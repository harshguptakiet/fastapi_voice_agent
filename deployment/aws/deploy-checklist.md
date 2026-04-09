# AWS Deployment Checklist

## Phase 1: Prerequisites (Manual)

1. Install and configure AWS CLI: `aws configure`.
2. Confirm account and region:
   - `aws sts get-caller-identity`
   - `aws configure get region`
3. Create or choose Route 53 hosted zone.
4. Request ACM certificate for:
   - `app.<your-domain>`
   - `api.<your-domain>`

## Phase 2: Repositories and Images (Manual + Commands)

1. Create ECR repositories:
   - `chatbot-frontend`
   - `fastapi-server`
   - `religious-bot`
   - `education-bot`
2. Build and push images.
3. Use immutable tags (commit SHA).

## Phase 3: Networking (Manual)

1. Create VPC with 2 AZs.
2. Create subnets:
   - 2 public for ALB
   - 2 private for ECS tasks
3. Attach NAT gateway for private egress.
4. Create security groups:
   - ALB SG: allow inbound 80/443
   - Frontend SG: allow from ALB on 3000
   - FastAPI SG: allow from ALB on 8001
   - Bots SG: allow from FastAPI SG on 8000 and 8002

## Phase 4: Secrets and Parameters (Manual)

1. Put API keys in Secrets Manager.
2. Put non-secret configs in SSM Parameter Store.
3. Reference them in ECS task definitions.

## Phase 5: ECS Setup (Manual + JSON Templates)

1. Create ECS cluster (Fargate).
2. Register task definitions from:
   - `deployment/aws/task-definitions/frontend.task.json`
   - `deployment/aws/task-definitions/fastapi-server.task.json`
   - `deployment/aws/task-definitions/religious-bot.task.json`
   - `deployment/aws/task-definitions/education-bot.task.json`
3. Create services:
   - Desired count >= 2 for frontend and fastapi
   - Desired count >= 1 for bots (start), then scale as needed

## Phase 6: Load Balancer and Routing (Manual)

1. Create internet-facing ALB.
2. Target groups:
   - frontend target group -> port 3000
   - fastapi target group -> port 8001
3. HTTPS listener (443) with ACM cert.
4. Listener rules:
   - host `app.<your-domain>` -> frontend target group
   - host `api.<your-domain>` -> fastapi target group
5. Route 53 records:
   - `app.<your-domain>` -> ALB
   - `api.<your-domain>` -> ALB

## Phase 7: Validation (Manual)

1. Hit health endpoints:
   - `https://api.<your-domain>/health`
   - `https://app.<your-domain>`
2. Validate cross-service calls from frontend to FastAPI and bots.
3. Validate voice websocket path:
   - `wss://api.<your-domain>/agent/ws`

## Phase 8: Observability and Operations (Manual)

1. Enable CloudWatch logs for all services.
2. Create alarms for:
   - ALB 5xx
   - p95 latency
   - ECS task restart count
3. Configure autoscaling policies.
4. Document rollback:
   - Re-deploy previous stable image tag.
