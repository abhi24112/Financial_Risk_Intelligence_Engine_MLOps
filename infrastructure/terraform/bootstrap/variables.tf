variable "aws_region" {
  description = "AWS region for the S3 state bucket"
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "terraform-lab"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "financial-risk-engine"
}

variable "state_bucket_name" {
  description = "Globally unique name for the Terraform remote state S3 bucket"
  type        = string
  default     = "abhishek-financial-risk-terraform-state-2026"
}
