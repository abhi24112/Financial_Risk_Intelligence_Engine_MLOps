output "state_bucket_name" {
  description = "Name of the remote state S3 bucket"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the remote state S3 bucket"
  value       = aws_s3_bucket.terraform_state.arn
}
