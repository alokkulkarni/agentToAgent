# Deployment Documentation Summary

This repository contains detailed, enterprise-grade deployment guides for the Agentic Framework.

## 1. Cloud-Specific Guides

*   **[AWS Deployment Guide](DEPLOYMENT_AWS.md)**
    *   **Serverless**: AWS Fargate (ECS)
    *   **Kubernetes**: Amazon EKS
    *   **VM/Legacy**: EC2 with Docker Swarm
    *   **Security**: VPC, IAM Roles, Secrets Manager

*   **[Azure Deployment Guide](DEPLOYMENT_AZURE.md)**
    *   **Serverless**: Azure Container Apps (ACA)
    *   **Kubernetes**: Azure Kubernetes Service (AKS)
    *   **VM/Legacy**: Virtual Machines with Docker Swarm
    *   **Security**: VNet, Managed Identities, Key Vault

## 2. General Deployment

*   **[General Deployment Guide](DEPLOYMENT.md)**
    *   Local Development (Docker Compose)
    *   Architecture Overview
    *   Prerequisites

## 3. Configuration

The framework is configured via Environment Variables to support "Twelve-Factor App" principles.
See `shared/config.py` for the full list of supported variables.

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REGISTRY_URL` | URL of the Service Registry | `http://registry:8000` |
| `AWS_REGION` | AWS Region for Bedrock | `us-east-1` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `ENABLE_GUARDRAILS` | Enable AI Safety Guardrails | `true` |
| `ENABLE_AUDIT_LOGGING` | Enable Compliance Logging | `true` |

## 4. Security Checklist

Before going to production:

1.  [ ] **Network**: Ensure all services run in Private Subnets/Private Endpoints.
2.  [ ] **Identity**: Use Managed Identities (Azure) or IAM Roles (AWS) instead of long-lived keys.
3.  [ ] **Secrets**: Store sensitive values in Key Vault/Secrets Manager.
4.  [ ] **Audit**: Enable WORM storage for audit logs (S3 Object Lock / Azure Blob Immutability).
