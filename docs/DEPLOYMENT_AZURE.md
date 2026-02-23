# Azure Deployment Guide for Agentic Framework

This guide provides granular, step-by-step instructions for deploying the Agentic Framework on Microsoft Azure. It covers three deployment patterns:
1.  **Serverless Containers (Azure Container Apps)** - Recommended for ease of management and KEDA scaling.
2.  **Kubernetes (Azure Kubernetes Service - AKS)** - Recommended for enterprise scale.
3.  **VM-based (Azure Virtual Machines with Docker Swarm)** - Legacy or specific compliance requirements.

All deployments assume a **Virtual Network (VNet)** setup for security.

---

## Prerequisites

*   Azure CLI installed (`az login`)
*   Docker installed (`docker`)
*   `kubectl` (for AKS)
*   Git

---

## Phase 1: Preparation & Artifacts

### 1.1. Create a Private Container Registry (ACR)

```bash
RESOURCE_GROUP="AgenticResourceGroup"
LOCATION="eastus"
ACR_NAME="agenticregistry$RANDOM"

# Create Resource Group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create ACR
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic

# Login to ACR
az acr login --name $ACR_NAME
ACR_URL="${ACR_NAME}.azurecr.io"
```

### 1.2. Build and Push Images
Run this from the root of the project.

```bash
# Build and Push Orchestrator
docker build -t $ACR_URL/agentic/orchestrator:latest -f services/orchestrator/Dockerfile .
docker push $ACR_URL/agentic/orchestrator:latest

# Build and Push Registry
docker build -t $ACR_URL/agentic/registry:latest -f services/registry/Dockerfile .
docker push $ACR_URL/agentic/registry:latest

# Repeat for all agents...
```

---

## Phase 2: Network & Security Setup (VNet)

1.  **Create VNet**: `10.0.0.0/16`
2.  **Subnets**:
    *   `infra-subnet`: For Application Gateway (Ingress).
    *   `apps-subnet`: For Container Apps or AKS Nodes. **Private endpoints only**.
3.  **Network Security Groups (NSG)**:
    *   Allow traffic on `8000-8100` only within `apps-subnet`.
    *   Deny direct Internet inbound.

---

## Phase 3: Deployment Options

### Option A: Azure Container Apps (ACA) - Recommended

1.  **Create Container App Environment**:
    ```bash
    az containerapp env create \
      --name agentic-env \
      --resource-group $RESOURCE_GROUP \
      --location $LOCATION \
      --infrastructure-subnet-resource-id <SUBNET_ID>
    ```

2.  **Deploy Registry Service**:
    ```bash
    az containerapp create \
      --name registry \
      --resource-group $RESOURCE_GROUP \
      --environment agentic-env \
      --image $ACR_URL/agentic/registry:latest \
      --target-port 8000 \
      --ingress internal \
      --min-replicas 1
    ```
    *Note: Internal ingress allows other apps in the env to call `http://registry`.*

3.  **Deploy Orchestrator**:
    ```bash
    az containerapp create \
      --name orchestrator \
      --resource-group $RESOURCE_GROUP \
      --environment agentic-env \
      --image $ACR_URL/agentic/orchestrator:latest \
      --target-port 8100 \
      --ingress external \
      --env-vars REGISTRY_URL=http://registry \
      --secrets aws-access-key=<VAL> aws-secret-key=<VAL>
    ```
    *Wait, `ingress external` exposes it. For strict security, use internal and expose via App Gateway.*

4.  **Deploy Agents**:
    Deploy other agents (Research, Math, etc.) with `--ingress internal`.
    Set `REGISTRY_URL=http://registry`.

---

### Option B: Azure Kubernetes Service (AKS)

1.  **Create Cluster**:
    ```bash
    az aks create \
      --resource-group $RESOURCE_GROUP \
      --name agentic-aks \
      --node-count 3 \
      --enable-addons monitoring \
      --generate-ssh-keys \
      --attach-acr $ACR_NAME \
      --vnet-subnet-id <SUBNET_ID>
    ```

2.  **Kubernetes Manifests**:
    Create standard K8s manifests (Deployment/Service) similar to the AWS Guide.
    
    *Difference: Secrets for Bedrock access*
    Since Bedrock is AWS, you need to inject AWS credentials into AKS.
    
    ```bash
    kubectl create secret generic aws-creds \
      --from-literal=AWS_ACCESS_KEY_ID=... \
      --from-literal=AWS_SECRET_ACCESS_KEY=...
    ```

    *Deployment Spec:*
    ```yaml
          env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: aws-creds
                  key: AWS_ACCESS_KEY_ID
            - name: AWS_REGION
              value: us-east-1
            - name: REGISTRY_URL
              value: "http://registry-service:8000"
    ```

---

### Option C: Azure VMs + Docker Swarm

1.  **Create VM Scale Set**:
    Create Linux VMs in the `apps-subnet`.

2.  **Install Docker**:
    Use `cloud-init` to install Docker.

3.  **Swarm Init**:
    Same process as AWS: `docker swarm init` on leader, `docker swarm join` on workers.

4.  **Azure Load Balancer**:
    Place a Layer 4 Load Balancer in front of the Swarm nodes, forwarding port 8100 to the Orchestrator.

---

## Phase 4: Enterprise Configuration

### 4.1. Secrets Management (Key Vault)
*   Create an **Azure Key Vault**.
*   Store `AWS_SECRET_ACCESS_KEY`, `OPENAI_API_KEY` (if used) there.
*   **ACA/AKS**: Use "Key Vault References" or "CSI Secret Store Driver" to mount these as volumes or env vars.

### 4.2. Identity (Managed Identity)
*   Assign a **User Assigned Managed Identity** to the Container Apps / AKS Nodes.
*   Use this identity to authenticate with **ACR** (pull images) and **Key Vault** (read secrets).
*   *Note*: Since the LLM is Bedrock (AWS), you still need AWS Keys. If using Azure OpenAI, use the Managed Identity for passwordless access!

### 4.3. Logging (Log Analytics)
*   ACA and AKS automatically integrate with **Azure Monitor / Log Analytics Workspace**.
*   Query logs:
    ```kusto
    ContainerLog
    | where Image contains "agentic"
    | where LogEntry contains "ERROR"
    ```

### 4.4. Cross-Cloud Connectivity (Bedrock Access)
*   Since the agents run in Azure but call AWS Bedrock:
    1.  Ensure egress traffic to `bedrock-runtime.us-east-1.amazonaws.com` is allowed in NSG/Firewall.
    2.  Recommended: Create an **AWS IAM User** dedicated to this Azure workload with specific `bedrock:InvokeModel` permissions. Rotate keys regularly or use OIDC federation (Azure AD -> AWS IAM) to avoid long-lived keys.

### 4.5. Vector Memory Store Configuration

The orchestrator ships with a pluggable vector memory backend. For Azure deployments, two native options are recommended:

#### Option A: Azure AI Search (recommended for keyword + semantic hybrid search)
```bash
# Create Azure AI Search service
az search service create \
  --name agentic-search \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku basic

# Get admin key (or use Managed Identity — omit AZURE_SEARCH_API_KEY)
AZURE_SEARCH_KEY=$(az search admin-key show \
  --service-name agentic-search \
  --resource-group $RESOURCE_GROUP \
  --query primaryKey -o tsv)
```
Set on orchestrator container/pod:
```
VECTOR_MEMORY_ENABLED=true
VECTOR_MEMORY_BACKEND=azure_ai_search
VECTOR_MEMORY_EMBEDDING=bedrock          # or openai / sentence_transformers
AZURE_SEARCH_ENDPOINT=https://agentic-search.search.windows.net
AZURE_SEARCH_API_KEY=<admin-key>         # omit if using Managed Identity
AZURE_SEARCH_INDEX=a2a-memories
AZURE_SEARCH_VECTOR_DIM=1536
```
Store `AZURE_SEARCH_API_KEY` in **Key Vault** and reference it via Key Vault Reference (ACA) or CSI Secret Store Driver (AKS). Managed Identity is preferred — omit the key entirely.

#### Option B: Azure Cosmos DB — DiskANN (recommended if already using Cosmos DB for session state)
```bash
# Create Cosmos DB account with vector search enabled
az cosmosdb create \
  --name agentic-cosmos \
  --resource-group $RESOURCE_GROUP \
  --locations regionName=$LOCATION \
  --capabilities EnableNoSQLVectorSearch

# Cosmos DB connection string (or use Managed Identity — omit COSMOS_KEY)
COSMOS_KEY=$(az cosmosdb keys list \
  --name agentic-cosmos \
  --resource-group $RESOURCE_GROUP \
  --query primaryMasterKey -o tsv)
```
Set on orchestrator container/pod:
```
VECTOR_MEMORY_ENABLED=true
VECTOR_MEMORY_BACKEND=azure_cosmos
VECTOR_MEMORY_EMBEDDING=bedrock
COSMOS_ENDPOINT=https://agentic-cosmos.documents.azure.com:443/
COSMOS_KEY=<primary-key>                 # omit if using Managed Identity
COSMOS_DATABASE=a2a_agent_memory
COSMOS_CONTAINER=agent_memories
COSMOS_VECTOR_POLICY=diskANN
```
Store `COSMOS_KEY` in **Key Vault**. For Managed Identity, assign the **Cosmos DB Built-in Data Contributor** role to the Container App / AKS pod identity.

#### Managed Identity (passwordless) — both backends
```bash
# Assign identity to Container App
az containerapp identity assign \
  --name orchestrator \
  --resource-group $RESOURCE_GROUP \
  --system-assigned

# Azure AI Search — assign Search Index Data Contributor role
az role assignment create \
  --assignee <PRINCIPAL_ID> \
  --role "Search Index Data Contributor" \
  --scope /subscriptions/<SUB_ID>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/agentic-search

# Cosmos DB — assign Built-in Data Contributor role
az cosmosdb sql role assignment create \
  --account-name agentic-cosmos \
  --resource-group $RESOURCE_GROUP \
  --role-definition-id 00000000-0000-0000-0000-000000000002 \
  --principal-id <PRINCIPAL_ID> \
  --scope /subscriptions/<SUB_ID>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/agentic-cosmos
```
With Managed Identity assigned, omit `AZURE_SEARCH_API_KEY` / `COSMOS_KEY` entirely — `DefaultAzureCredential` is used automatically.
