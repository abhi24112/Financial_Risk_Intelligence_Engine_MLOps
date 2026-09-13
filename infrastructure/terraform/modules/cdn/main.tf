# infrastructure/terraform/modules/cdn/main.tf
# Provides free AWS SSL/HTTPS front-door for the Application Load Balancer

resource "aws_cloudfront_distribution" "api_cdn" {
  origin {
    domain_name = var.alb_dns_name
    origin_id   = "${var.project_name}-${var.environment}-alb-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB listens on port 80
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled         = true
  is_ipv6_enabled = true
  comment         = "Free HTTPS CloudFront CDN for Financial Risk Engine"

  default_cache_behavior {
    # Allow all HTTP methods so POST /predict and GET /health work
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "${var.project_name}-${var.environment}-alb-origin"

    # Automatically redirects any http:// to https://
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = true
      headers      = ["Accept", "Authorization", "Content-Type", "Origin", "Referer"]
      cookies {
        forward = "all"
      }
    }

    # Set TTL to 0 so API responses are always REAL-TIME (no stale cache!)
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Uses the 100% FREE official Amazon SSL Certificate (*.cloudfront.net)
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = var.tags
}
