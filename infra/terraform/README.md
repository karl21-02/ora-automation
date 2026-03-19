# Mimir Backend - GCP Terraform Deployment

One-shot deployment: VM + Docker (API + PostgreSQL + RabbitMQ)

## Prerequisites

1. GCP Project with billing enabled
2. `gcloud` CLI installed and authenticated
3. Terraform >= 1.0

## Quick Start

```bash
# 1. Authenticate
gcloud auth application-default login

# 2. Enable required APIs
gcloud services enable compute.googleapis.com

# 3. Configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 4. Deploy
terraform init
terraform apply
```

## After Deployment

```bash
# Get outputs
terraform output

# SSH into server
$(terraform output -raw ssh_command)

# Check logs
$(terraform output -raw logs_command)

# Check Docker status
gcloud compute ssh mimir-backend --zone=asia-northeast3-a --command='cd /opt/mimir/app && docker compose ps'
```

## Costs

- **e2-medium** (2 vCPU, 4GB): ~$25/month
- **50GB SSD**: ~$8/month
- **Static IP**: ~$3/month
- **Total**: ~$36/month

## Destroy

```bash
terraform destroy
```
