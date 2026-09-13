# infrastructure/terraform/environments/dev/main.tf
# Orchestration of all child modules for dev environment

# 1. Multi-AZ Networking
module "networking" {
  source = "../../modules/networking"

  project_name         = var.project_name
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  tags                 = local.common_tags
}

# 2. Security Groups & Rules
module "security" {
  source = "../../modules/security"

  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.networking.vpc_id
  tags         = local.common_tags
}

# 3. IAM Roles (Execution & Task)
module "iam" {
  source = "../../modules/iam"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.common_tags
}

# 4. Database (PostgreSQL 16)
module "database" {
  source = "../../modules/database"

  project_name          = var.project_name
  environment           = var.environment
  private_subnet_ids    = module.networking.private_subnet_ids
  rds_security_group_id = module.security.rds_security_group_id
  db_name               = var.db_name
  db_username           = var.db_username
  db_password           = var.db_password
  tags                  = local.common_tags
}

# 5. Cache (Redis 7 Feature Store)
module "cache" {
  source = "../../modules/cache"

  project_name            = var.project_name
  environment             = var.environment
  private_subnet_ids      = module.networking.private_subnet_ids
  redis_security_group_id = module.security.redis_security_group_id
  tags                    = local.common_tags
}

# 6. Load Balancer (ALB + Target Group)
module "load_balancer" {
  source = "../../modules/load_balancer"

  project_name          = var.project_name
  environment           = var.environment
  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  alb_security_group_id = module.security.alb_security_group_id
  tags                  = local.common_tags
}

# 7. Compute (ECR + ECS Fargate + CloudWatch)
module "compute" {
  source = "../../modules/compute"

  project_name           = var.project_name
  environment            = var.environment
  private_subnet_ids     = module.networking.private_subnet_ids
  ecs_security_group_id  = module.security.ecs_security_group_id
  ecs_execution_role_arn = module.iam.ecs_execution_role_arn
  ecs_task_role_arn      = module.iam.ecs_task_role_arn
  target_group_arn       = module.load_balancer.target_group_arn

  db_endpoint = module.database.db_address
  db_name     = module.database.db_name
  db_username = var.db_username
  db_password = var.db_password

  redis_endpoint  = module.cache.redis_endpoint
  redis_port      = module.cache.redis_port
  container_image = var.container_image

  tags = local.common_tags
}

# 8. CloudFront HTTPS Front-Door
module "cdn" {
  source = "../../modules/cdn"

  project_name = var.project_name
  environment  = var.environment
  alb_dns_name = module.load_balancer.alb_dns_name
  tags         = local.common_tags
}

