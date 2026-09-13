# CI/CD Pipeline: GitHub Actions, AWS ECR & AWS ECS

This document describes the automated Continuous Integration and Continuous Deployment (CI/CD) pipeline for the **Adaptive Financial Risk Intelligence Engine**. It covers how code is automatically tested, containerized, stored in Amazon ECR, and deployed with zero downtime to Amazon ECS (Fargate).

---

## 1. Overview & Objectives

The primary objective of this CI/CD pipeline is to ensure that only tested, production-ready code is built into containers and deployed to cloud infrastructure.

```mermaid
flowchart LR
    subgraph GitHub
        A[Git Push / PR to main] --> B{Path Filter Check}
        B -- "Docs/Notebooks/Airflow" --> C[Workflow Skipped ⏭️]
        B -- "api/, ml/, configs/, Dockerfile.api" --> D[Stage 1: Smoke Tests 🧪]
        D --> E{Tests Pass?}
        E -- No --> F[Fail Fast & Abort ❌]
        E -- Yes --> G[Stage 2: Build & Push Docker 🐳]
    end

    subgraph AWS Cloud
        G --> H[Amazon ECR: Tag SHA + latest]
        H --> I[Stage 3: Trigger ECS Deployment 🚀]
        I --> J[AWS ECS Fargate: Rolling Zero-Downtime Update]
    end
```

### Key Pillars
1. **Intelligent Path Filtering (`paths:` rule)**: Rebuilds and deploys containers **only** when files critical to the API container change.
2. **Fail-Fast Smoke Testing**: Runs lightweight, standalone tests (<10 seconds) before container build to catch import errors, bad YAML configurations, or broken Pydantic schemas.
3. **Automated Docker Packaging & ECR Versioning**: Builds `docker/Dockerfile.api` and tags the image with both the unique Git commit SHA (`${{ github.sha }}`) and `latest`.
4. **Zero-Downtime ECS Rolling Deployment**: Signals AWS ECS Fargate via `aws ecs update-service --force-new-deployment` to start new tasks, perform ALB health checks, and safely drain old tasks without dropping user requests.

---

## 2. Path Filtering Strategy: Why and How

In a comprehensive MLOps repository, changes can be made to Airflow DAGs, DVC data manifests, documentation, Jupyter notebooks, or Terraform scripts that do not require updating the serving container.

### Monitored Paths
The GitHub Actions workflow triggers **only** when changes occur in these directories and files:

```yaml
paths:
  - 'api/**'                     # FastAPI endpoints, routers, schemas, middleware
  - 'configs/**'                 # api.yaml, model.yaml, paths.yaml
  - 'database/**'                # DB connection, queries, schema
  - 'explainability/**'          # SHAP engine, analyst explanation logic
  - 'feature_store/**'           # Redis feature retrieval & schemas
  - 'ml/**'                      # Model inference, thresholding, calibration
  - 'models/**'                  # Serialized model artifacts
  - 'pipelines/**'               # Pipeline classes
  - 'shared/**'                  # Logging, exceptions, config loaders
  - 'main.py'                    # Application entrypoint
  - 'requirements.txt'           # Python dependency manifests
  - 'docker/Dockerfile.api'      # Container build recipe
  - 'tests/unit/test_ci_smoke.py'# CI smoke test suite
  - '.github/workflows/ci_cd.yml'# CI/CD definition itself
```

### Files That Do NOT Trigger Container Redeployment
- `Doc/**` / `docs/**` (Documentation updates)
- `notebooks/**` (Data science experimentation)
- `airflow/**` (Airflow orchestration DAGs)
- `dataset/**` / `data/**` (Local CSV datasets)
- `infrastructure/terraform/**` (IaC infrastructure code)
- `README.md`, `.gitignore`

---

## 3. Pipeline Stages Breakdown

The workflow is defined in [`.github/workflows/ci_cd.yml`](file:///c:/Users/Abhishek/Desktop/MLOps/Adaptive%20Financial%20Risk%20Intelligence%20Engine/.github/workflows/ci_cd.yml).

### Stage 1: Automated Smoke Testing (`smoke-test`)
- **Environment**: `ubuntu-latest`, Python `3.12`.
- **Cache**: Uses `actions/setup-python` with `cache: 'pip'` for fast execution.
- **Execution**: Runs `pytest tests/unit/test_ci_smoke.py -v`.
- **What it tests**:
  1. **Config Integrity**: Verifies `configs/api.yaml` and `configs/model.yaml` exist and are valid YAML.
  2. **Schema Contracts**: Verifies `TransactionRequest` accepts valid transactions and rejects invalid values (e.g. `TransactionAmt <= 0`).
  3. **Batch Handling**: Verifies `BatchTransactionRequest` rejects empty batches.
  4. **FastAPI Application Health**: Initializes the application factory (`create_app()`) and validates that `/health` returns HTTP 200 with required keys (`status`, `model_loaded`, `version`).

### Stage 2: Build & Push to Amazon ECR (`build-and-push-ecr`)
- **Prerequisite**: Depends on `smoke-test` passing (`needs: smoke-test`).
- **Condition**: Executes on merge/push to `main` branch or manual trigger (`workflow_dispatch`).
- **AWS Authentication**:
  - `aws-actions/configure-aws-credentials@v4` authenticates securely using GitHub Secrets.
  - `aws-actions/amazon-ecr-login@v2` logs Docker CLI into the Amazon ECR registry.
- **Docker Build & Tag**:
  ```bash
  docker build -f docker/Dockerfile.api \
    -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
    -t $ECR_REGISTRY/$ECR_REPOSITORY:latest .
  ```
- **Pushing**: Pushes both tags to ECR.

### Stage 3: Zero-Downtime Deployment to AWS ECS (`deploy-ecs`)
- **Prerequisite**: Depends on `build-and-push-ecr` passing.
- **Resilient Execution**:
  The workflow dynamically queries AWS ECS to verify whether the service is currently `ACTIVE`:
  - **If the service is active**: It triggers `aws ecs update-service --force-new-deployment` to roll out the newly pushed container image.
  - **If the service is inactive/torn down (e.g. for cost savings)**: It reports that the container was successfully built and pushed to Amazon ECR, completing the workflow without failing.
- **How ECS Fargate Executes Rolling Updates**:
  1. ECS reads the task definition and pulls the fresh image from ECR.
  2. ECS launches new Fargate tasks alongside the old tasks.
  3. AWS Application Load Balancer (ALB) executes health checks against `/health`.
  4. Once new tasks pass health checks, traffic is smoothly routed to new tasks.
  5. Connections on old tasks are drained and terminated.

---

## 4. Terraform Infrastructure Alignment

The CI/CD pipeline is designed to map directly to the Terraform resources defined in `infrastructure/terraform/`:

| CI/CD Component | Matching Terraform Resource | Location in Terraform |
|---|---|---|
| **ECR Registry** | `aws_ecr_repository.api` | `modules/compute/main.tf` (`financial-risk-engine-dev-api`) |
| **ECS Cluster** | `aws_ecs_cluster.main` | `modules/compute/main.tf` (`financial-risk-engine-dev-cluster`) |
| **ECS Fargate Service** | `aws_ecs_service.api` | `modules/compute/main.tf` (`financial-risk-engine-dev-api-service`) |
| **ECS Task Definition** | `aws_ecs_task_definition.api` | `modules/compute/main.tf` (`risk-engine-api` container, Port 8000) |
| **Health Check Endpoint** | `aws_lb_target_group.api` | `modules/load_balancer/main.tf` (`/health` matcher 200) |
| **Security Groups** | `aws_security_group.ecs`, `aws_security_group.alb` | `modules/security/main.tf` (Strict ALB ➔ ECS 8000 chaining) |


---

## 5. Required GitHub Repository Secrets

Configure these secrets in GitHub: **Repository -> Settings -> Secrets and variables -> Actions**:

| Secret Name | Description | Example / Default |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | IAM User Access Key with ECR & ECS permissions | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | IAM User Secret Access Key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | Target AWS Region | `ap-south-1` |
| `ECR_REPOSITORY` | Amazon ECR Repository Name | `financial-risk-engine-dev-api` |
| `ECS_CLUSTER` | Amazon ECS Cluster Name | `financial-risk-engine-dev-cluster` |
| `ECS_SERVICE` | Amazon ECS Service Name | `financial-risk-engine-dev-api-service` |

---

## 6. Local Testing & Verification

### Running the Smoke Test Locally
Ensure the conda environment is active and execute:
```bash
conda run -n financial_risk_intelligence pytest tests/unit/test_ci_smoke.py -v
```

### Testing the Docker Image Locally
```bash
# Build the API container locally
docker build -f docker/Dockerfile.api -t financial-risk-api:test .

# Run container
docker run -d -p 8000:8000 --name test-api financial-risk-api:test

# Check container health probe
curl http://localhost:8000/health
```

---

## 7. Interview Questions & Expert Answers

### Q1: Why did you implement path filtering in GitHub Actions?
> **Answer**: In an MLOps repository, many commits touch documentation, exploratory notebooks, or Airflow DAGs. Without path filtering, every single commit would trigger a multi-minute Docker build and redeploy the cloud microservice, wasting CI minutes and causing unnecessary redeployments. By restricting triggers to files inside the container build context (`api/`, `ml/`, `configs/`, `Dockerfile.api`), we ensure deployments happen **only when the API serving layer is actually modified**.

### Q2: Why run smoke tests before building the Docker image?
> **Answer**: This follows the **Fail-Fast** engineering principle. Building a multi-stage Docker image and uploading several hundred megabytes to AWS ECR takes 3–5 minutes. If there is a syntax error, broken import, or schema validation failure, running a 5-second smoke test catches it immediately before consuming network bandwidth or AWS resources.

### Q3: How do you achieve zero downtime when deploying updates to ECS?
> **Answer**: We use AWS ECS rolling deployment with Fargate and an Application Load Balancer. When `aws ecs update-service --force-new-deployment` is called, ECS spins up the new task version, waits for container initialization, and monitors the `/health` endpoint via the ALB target group. Traffic is routed to the new task only when it is verified healthy, after which old tasks are drained gracefully.

### Q4: Why tag Docker images with both the Git SHA and `latest`?
> **Answer**: The Git SHA tag (e.g. `c7a4f91`) is **immutable** and provides auditability—every running container can be traced directly back to the exact Git commit that produced it. This makes instant rollbacks possible. The `latest` tag provides convenience for development and automated task definitions.

### Q5: How would you roll back if an issue occurs in production?
> **Answer**: Because every build is tagged with its unique Git SHA in Amazon ECR, rolling back takes seconds: we can either run `aws ecs update-service` pointing to the previous known-good Git SHA tag or rerun the GitHub Actions workflow on the previous stable commit using `workflow_dispatch`.
