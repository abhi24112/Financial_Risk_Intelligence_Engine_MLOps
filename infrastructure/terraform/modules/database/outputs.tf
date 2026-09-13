output "db_endpoint" {
  description = "Connection endpoint for the RDS PostgreSQL database"
  value       = aws_db_instance.postgres.endpoint
}

output "db_address" {
  description = "Hostname of the RDS PostgreSQL database"
  value       = aws_db_instance.postgres.address
}

output "db_port" {
  description = "Port of the RDS PostgreSQL database"
  value       = aws_db_instance.postgres.port
}

output "db_name" {
  description = "Name of the RDS database"
  value       = aws_db_instance.postgres.db_name
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret holding database credentials"
  value       = aws_secretsmanager_secret.db_secret.arn
}
