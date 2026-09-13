# infrastructure/terraform/environments/dev/backend.tf

terraform {
  backend "s3" {
    bucket       = "abhishek-financial-risk-terraform-state-2026"
    key          = "risk_engine/dev/terraform.tfstate"
    region       = "ap-south-1"
    profile      = "terraform-lab"
    use_lockfile = true
  }
}
