variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for DB Subnet Group"
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

variable "db_name" {
  description = "Name of the default database to create"
  type        = string
  default     = "fraud_risk"
}

variable "db_username" {
  description = "Master username for RDS"
  type        = string
  default     = "fraud_user"
}

variable "db_password" {
  description = "Master password for RDS (sensitive)"
  type        = string
  sensitive   = true
  default     = "FinancialRiskAdmin2026!"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
