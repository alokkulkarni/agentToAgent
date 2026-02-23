# AWS Deployment Guide for Agentic Framework

This guide provides detailed, granular instructions for deploying the Agentic Framework on Amazon Web Services (AWS) using either **Amazon EKS (Kubernetes)** or **AWS Lambda (Serverless)**.

All deployments assume a **Virtual Private Cloud (VPC)** setup for security.

---

## 1. Prerequisites (Common for Both Options)

### 1.1. VPC & Network Setup
Create a secure VPC with public and private subnets.

```bash
# Create VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16

# Create Subnets
aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.0.1.0/24 --availability-zone us-east-1a # Public
aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.0.2.0/24 --availability-zone us-east-1a # Private

# Create Internet Gateway & NAT Gateway
# (Standard AWS setup: IGW for Public Subnet, NAT GW in Public Subnet for Private Subnet outbound access)
```

### 1.2. (Optional) AWS Chime SDK Setup
If your agents require voice or video capabilities using AWS Chime SDK, you need to configure specific permissions.
Refer to [CHIME_SETUP_GUIDE.md](./CHIME_SETUP_GUIDE.md) for detailed instructions on configuring `chime.amazonaws.com` service principal permissions.

### 1.3. Container Registry (ECR)
Create repositories for all services.

```bash
REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Login
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URL

# Create Repos
SERVICES=("orchestrator" "registry" "mcp-gateway" "mcp-server-web-search" "agent-math" "agent-research" "agent-data-processor" "agent-task-executor" "agent-observer" "agent-code-analyzer")

for svc in "${SERVICES[@]}"; do
  aws ecr create-repository --repository-name "agentic/$svc" --region $REGION
done
```

### 1.3. Build & Push Images
From project root:

```bash
# Orchestrator
docker build -t $ECR_URL/agentic/orchestrator:latest -f services/orchestrator/Dockerfile .
docker push $ECR_URL/agentic/orchestrator:latest

# Registry
docker build -t $ECR_URL/agentic/registry:latest -f services/registry/Dockerfile .
docker push $ECR_URL/agentic/registry:latest

# MCP Gateway
docker build -t $ECR_URL/agentic/mcp-gateway:latest -f services/mcp_gateway/Dockerfile .
docker push $ECR_URL/agentic/mcp-gateway:latest

# MCP Server (Web Search)
docker build -t $ECR_URL/agentic/mcp-server-web-search:latest -f services/mcp_servers/web_search/Dockerfile .
docker push $ECR_URL/agentic/mcp-server-web-search:latest

# MCP Server (Calculator)
docker build -t $ECR_URL/agentic/mcp-server-calculator:latest -f services/mcp_servers/calculator/Dockerfile .
docker push $ECR_URL/agentic/mcp-server-calculator:latest

# MCP Server (Database)
docker build -t $ECR_URL/agentic/mcp-server-database:latest -f services/mcp_servers/database/Dockerfile .
docker push $ECR_URL/agentic/mcp-server-database:latest

# MCP Server (File Ops)
docker build -t $ECR_URL/agentic/mcp-server-file-ops:latest -f services/mcp_servers/file_ops/Dockerfile .
docker push $ECR_URL/agentic/mcp-server-file-ops:latest

# MCP Registry
docker build -t $ECR_URL/agentic/mcp-registry:latest -f services/mcp_registry/Dockerfile .
docker push $ECR_URL/agentic/mcp-registry:latest

# Agents
docker build -t $ECR_URL/agentic/agent-math:latest -f services/agents/math_agent/Dockerfile .
docker push $ECR_URL/agentic/agent-math:latest

docker build -t $ECR_URL/agentic/agent-research:latest -f services/agents/research_agent/Dockerfile .
docker push $ECR_URL/agentic/agent-research:latest

docker build -t $ECR_URL/agentic/agent-data-processor:latest -f services/agents/data_processor/Dockerfile .
docker push $ECR_URL/agentic/agent-data-processor:latest

docker build -t $ECR_URL/agentic/agent-task-executor:latest -f services/agents/task_executor/Dockerfile .
docker push $ECR_URL/agentic/agent-task-executor:latest

docker build -t $ECR_URL/agentic/agent-observer:latest -f services/agents/observer/Dockerfile .
docker push $ECR_URL/agentic/agent-observer:latest

docker build -t $ECR_URL/agentic/agent-code-analyzer:latest -f services/agents/code_analyzer/Dockerfile .
docker push $ECR_URL/agentic/agent-code-analyzer:latest
```

### 1.4. Redis (ElastiCache)
Create a Redis cluster in the **Private Subnet**.
*   **Security Group**: Allow TCP 6379 from the Private Subnet CIDR (10.0.2.0/24).
*   **Endpoint**: Note the primary endpoint (e.g., `redis-cluster.xyz.cache.amazonaws.com`).

---

## Option A: Amazon EKS (Kubernetes) Deployment

### Architecture
```ascii
[ Internet ] -> [ ALB Ingress ] -> [ Orchestrator Service ] -> [ Redis ]
                                            |
                                            v
                                   [ Internal K8s Services ]
          +----------------+----------------+----------------+----------------+
          |                |                |                |                |
    [ Registry ]    [ MCP Gateway ]  [ Math Agent ]  [ Research Agent ]  [ ... ]
                           |
                    [ Web Search MCP ]
```

### 2.1. Cluster Creation
```bash
eksctl create cluster --name agentic-cluster --region $REGION --nodegroup-name standard-workers --node-type t3.medium --nodes 3 --managed
```

### 2.2. Configuration (ConfigMap & Secrets)
Create `k8s/config-env.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
  namespace: default
data:
  # Internal Service DNS names in K8s
  REGISTRY_URL: "http://registry-service:8000"
  MCP_GATEWAY_URL: "http://mcp-gateway-service:8000"
  REDIS_HOST: "<YOUR_ELASTICACHE_ENDPOINT>"
  REDIS_PORT: "6379"
  LOG_LEVEL: "INFO"
  # ── Vector Memory Store ────────────────────────────────────────────────────
  # Option A: disabled (safe default)
  VECTOR_MEMORY_ENABLED: "false"
  VECTOR_MEMORY_BACKEND: "in_memory"
  VECTOR_MEMORY_EMBEDDING: "bedrock"
  VECTOR_MEMORY_COLLECTION: "a2a_memories"
  VECTOR_MEMORY_TOP_K: "5"
  VECTOR_MEMORY_SCORE_THRESHOLD: "0.3"
  BEDROCK_EMBED_MODEL: "amazon.titan-embed-text-v1"
  # Option B: AWS OpenSearch Service (recommended for AWS deployments)
  # VECTOR_MEMORY_ENABLED: "true"
  # VECTOR_MEMORY_BACKEND: "opensearch_aws"
  # OPENSEARCH_HOST: "https://search-<name>-<id>.us-east-1.es.amazonaws.com"
  # OPENSEARCH_SERVICE: "es"        # es = managed domain, aoss = serverless
  # OPENSEARCH_REGION: "us-east-1"
  # OPENSEARCH_INDEX: "a2a-memories"
  # OPENSEARCH_VECTOR_DIM: "1536"
  # Note: Auth uses SigV4 automatically from the pod's IAM role — no extra secrets.
```

Create `k8s/secrets.yaml` (Replace with actual keys):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: agent-secrets
  namespace: default
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "..."
  AWS_SECRET_ACCESS_KEY: "..."
  BEDROCK_REGION: "us-east-1"
  # Vector memory secrets — only needed if NOT using IAM role (pod identity)
  # OPENSEARCH_USER: "admin"           # basic auth fallback only
  # OPENSEARCH_PASSWORD: "..."
  # PINECONE_API_KEY: "pc-..."         # if using Pinecone instead
```
Apply: `kubectl apply -f k8s/config-env.yaml -f k8s/secrets.yaml`

#### IAM Policy — OpenSearch vector memory (EKS IRSA / EC2 instance profile)
If using `VECTOR_MEMORY_BACKEND=opensearch_aws`, attach this policy to the orchestrator pod's service account role:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "es:ESHttpGet",
      "es:ESHttpPost",
      "es:ESHttpPut",
      "es:ESHttpDelete",
      "es:ESHttpHead"
    ],
    "Resource": "arn:aws:es:<REGION>:<ACCOUNT_ID>:domain/<DOMAIN_NAME>/*"
  }]
}
```
For OpenSearch Serverless (`OPENSEARCH_SERVICE=aoss`), replace `es:ESHttp*` with `aoss:APIAccessAll`.
The orchestrator authenticates via SigV4 using the pod's IAM role — **no hardcoded keys required**.

### 2.3. Service Deployments
Create YAML files for each service.

**1. Registry Service (`k8s/registry.yaml`)**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: registry
spec:
  replicas: 1
  selector:
    matchLabels:
      app: registry
  template:
    metadata:
      labels:
        app: registry
    spec:
      containers:
      - name: registry
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/registry:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: registry-service
spec:
  selector:
    app: registry
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
```

**2. MCP Registry (`k8s/mcp-registry.yaml`)**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-registry
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-registry
  template:
    metadata:
      labels:
        app: mcp-registry
    spec:
      containers:
      - name: mcp-registry
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/mcp-registry:latest
        ports:
        - containerPort: 8200
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-registry-service
spec:
  selector:
    app: mcp-registry
  ports:
    - protocol: TCP
      port: 8200
      targetPort: 8200
```

**3. MCP Gateway (`k8s/mcp-gateway.yaml`)**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-gateway
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-gateway
  template:
    metadata:
      labels:
        app: mcp-gateway
    spec:
      containers:
      - name: mcp-gateway
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/mcp-gateway:latest
        ports:
        - containerPort: 8300
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-gateway-service
spec:
  selector:
    app: mcp-gateway
  ports:
    - protocol: TCP
      port: 8300
      targetPort: 8300
```

**4. MCP Servers**
Deploy each MCP server:
*   **Web Search** (`k8s/mcp-server-web-search.yaml`) - Port 8212
*   **Calculator** (`k8s/mcp-server-calculator.yaml`) - Port 8213
*   **Database** (`k8s/mcp-server-database.yaml`) - Port 8211
*   **File Ops** (`k8s/mcp-server-file-ops.yaml`) - Port 8210

Example for `Web Search`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server-web-search
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server-web-search
  template:
    metadata:
      labels:
        app: mcp-server-web-search
    spec:
      containers:
      - name: mcp-server-web-search
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/mcp-server-web-search:latest
        ports:
        - containerPort: 8212
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server-web-search-service
spec:
  selector:
    app: mcp-server-web-search
  ports:
    - protocol: TCP
      port: 8212
      targetPort: 8212
```

**5. Agents**
Deploy each agent with correct ports:
*   **Research Agent** (`agent-research`) - Port 8003
*   **Math Agent** (`agent-math`) - Port 8006
*   **Data Processor** (`agent-data-processor`) - Port 8002
*   **Task Executor** (`agent-task-executor`) - Port 8004
*   **Observer** (`agent-observer`) - Port 8005
*   **Code Analyzer** (`agent-code-analyzer`) - Port 8001

Example for `ResearchAgent` (`k8s/agent-research.yaml`):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-research
spec:
  replicas: 1
  selector:
    matchLabels:
      app: agent-research
  template:
    metadata:
      labels:
        app: agent-research
    spec:
      containers:
      - name: agent-research
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/agent-research:latest
        ports:
        - containerPort: 8003
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: agent-research-service
spec:
  selector:
    app: agent-research
  ports:
    - protocol: TCP
      port: 8003
      targetPort: 8003
```

**6. Orchestrator (`k8s/orchestrator.yaml`)**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: orchestrator
        image: <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/agentic/orchestrator:latest
        ports:
        - containerPort: 8100
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: orchestrator-service
spec:
  selector:
    app: orchestrator
  ports:
    - protocol: TCP
      port: 8100
      targetPort: 8100
```

### 2.4. Ingress (Exposing Orchestrator)
Install **AWS Load Balancer Controller** first. Then:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orchestrator-ingress
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: orchestrator-service
                port:
                  number: 8100
```

---

## Option B: AWS Serverless (Lambda) Deployment

### Architecture
```ascii
[ Internet ] -> [ API Gateway ] -> [ Lambda: Orchestrator ]
                                          |
                                          v
                                   [ AWS Cloud Map ]
                                          |
       +------------------+---------------+------------------+
       |                  |               |                  |
[ Lambda: Registry ] [ Lambda: Math ] [ Lambda: Research ] [ ... ]
```

### 3.1. AWS Cloud Map (Service Discovery)
Create a private namespace for service discovery.
```bash
aws servicediscovery create-private-dns-namespace --name "agentic.local" --vpc <VPC_ID>
```

### 3.2. Lambda Function Configuration
For each service, you will create a Lambda function using the **Container Image** from ECR.

**Common Configuration:**
*   **Package Type**: Image
*   **Memory**: 512MB - 1024MB
*   **Timeout**: 30-60 seconds (Orchestrator might need more)
*   **VPC**: Attach to Private Subnets.
*   **Security Group**: Allow outbound to 443 (Bedrock/AWS APIs) and internal communication.

**Environment Variables:**
*   `REGISTRY_URL`: `http://registry.agentic.local:8000` (Resolved via Cloud Map)
*   `MCP_GATEWAY_URL`: `http://mcp-gateway.agentic.local:8000`
*   `AWS_LAMBDA_EXEC_WRAPPER`: `/opt/bootstrap` (If using custom runtime, but for Python Container images, ensure entrypoint handles Lambda events or use **AWS Lambda Web Adapter**).

**CRITICAL: AWS Lambda Web Adapter**
Since our agents are written as web servers (Flask/FastAPI), simply deploying them as standard Lambdas won't work because Lambda expects an event handler, not a listening socket.
**Solution**: Use the **AWS Lambda Web Adapter** layer or extension.
1.  In your `Dockerfile`, add the adapter:
    ```dockerfile
    COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.7.0 /lambda-adapter /opt/extensions/lambda-adapter
    ```
2.  This adapter translates API Gateway/ALB events into HTTP requests for your Flask/FastAPI app running on localhost within the Lambda environment.

### 3.3. Deployment Steps (Example: Research Agent)

1.  **Update Dockerfile** to include Lambda Adapter (as above).
2.  **Rebuild & Push** image.
3.  **Create Lambda Function**:
    ```bash
    aws lambda create-function --function-name Agentic-ResearchAgent \
      --package-type Image \
      --code ImageUri=$ECR_URL/agentic/agent-research:latest \
      --role arn:aws:iam::<ACCOUNT_ID>:role/service-role/AgenticLambdaRole \
      --vpc-config SubnetIds=<PRIVATE_SUBNETS>,SecurityGroupIds=<SG_ID>
    ```
4.  **Register in Cloud Map**:
    *   Create a Service in Cloud Map `agent-research`.
    *   Register an Instance for the Lambda (or use an Internal Application Load Balancer in front of Lambda if direct invocation is complex).
    *   **Simpler Alternative**: Use **Function URL** (if auth allows) or **Internal ALB**.
    *   **Best Enterprise Practice**: Put an **Internal Application Load Balancer (ALB)** in front of the Agent Lambdas.
        *   Create Target Group (Type: Lambda).
        *   Register `Agentic-ResearchAgent` to Target Group.
        *   Create Listener Rule on Internal ALB: `Host: agent-research.agentic.local` -> Forward to Target Group.

### 3.4. Orchestrator Deployment
1.  Deploy `Orchestrator` as a Lambda (with Web Adapter).
2.  Create an **HTTP API Gateway** or **Public ALB**.
3.  Point the API Gateway route `ANY /{proxy+}` to the Orchestrator Lambda.

### 3.5. Connecting Services
*   **Orchestrator -> Agents**: Orchestrator calls `http://agent-research.agentic.local:8003`.
*   **DNS Resolution**: The Internal ALB has a DNS name. Use Route53 Private Hosted Zone `agentic.local` to alias `agent-research.agentic.local` to the Internal ALB DNS name.

---

## 4. Verification

1.  **Health Check**:
    Curl the Orchestrator's public endpoint:
    ```bash
    curl https://<ORCHESTRATOR_ALB_OR_API_GW>/health
    ```

2.  **Run Workflow**:
    ```bash
    curl -X POST https://<ORCHESTRATOR_ALB>/api/workflow \
      -H "Content-Type: application/json" \
      -d '{"task": "Calculate pi"}'
    ```
