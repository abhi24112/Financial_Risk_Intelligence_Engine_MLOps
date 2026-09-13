# infrastructure/terraform/environments/dev/outputs.tf

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = module.load_balancer.alb_dns_name
}

output "api_health_check_url" {
  description = "Public URL for the Risk Engine API health check endpoint"
  value       = "http://${module.load_balancer.alb_dns_name}/health"
}

output "api_docs_url" {
  description = "Public URL for the Risk Engine interactive Swagger documentation"
  value       = "http://${module.load_balancer.alb_dns_name}/docs"
}

output "ecr_repository_url" {
  description = "URI of the ECR repository to push Docker images"
  value       = module.compute.ecr_repository_url
}

output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster"
  value       = module.compute.ecs_cluster_name
}

output "ecs_service_name" {
  description = "Name of the ECS service running the FastAPI tasks"
  value       = module.compute.ecs_service_name
}

output "db_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.db_endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.cache.redis_endpoint
}

output "vpc_id" {
  description = "ID of the provisioned VPC"
  value       = module.networking.vpc_id
}

output "https_api_url" {
  description = "Public HTTPS URL for phone and desktop browsers (with valid SSL)"
  value       = "https://${module.cdn.cloudfront_domain_name}"
}

output "https_api_docs_url" {
  description = "Public HTTPS interactive Swagger API documentation"
  value       = "https://${module.cdn.cloudfront_domain_name}/docs"
}

output "https_api_health_url" {
  description = "Public HTTPS health check URL"
  value       = "https://${module.cdn.cloudfront_domain_name}/health"
}

