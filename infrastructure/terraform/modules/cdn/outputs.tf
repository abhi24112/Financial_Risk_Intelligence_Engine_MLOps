output "cloudfront_domain_name" {
  description = "Public HTTPS domain name provided by CloudFront"
  value       = aws_cloudfront_distribution.api_cdn.domain_name
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.api_cdn.id
}
