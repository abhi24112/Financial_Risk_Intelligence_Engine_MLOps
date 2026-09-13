variable "aws_region" {
  description = "AWS Region to deploy resources into"
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "AWS CLI profile name"
  type        = string
  default     = "terraform-lab"
}

variable "project_name" {
  description = "Project identifier"
  type        = string
  default     = "financial-risk-engine"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks (2 AZs)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks (2 AZs)"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "db_username" {
  description = "PostgreSQL DB username"
  type        = string
  default     = "fraud_user"
}

variable "db_password" {
  description = "PostgreSQL DB password"
  type        = string
  sensitive   = true
  default     = "FinancialRiskAdmin2026!"
}

variable "db_name" {
  description = "PostgreSQL default database name"
  type        = string
  default     = "fraud_risk"
}

variable "container_image" {
  description = "Optional pre-existing container image URI"
  type        = string
  default     = ""
}
