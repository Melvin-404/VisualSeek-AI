# Main entry point for IaC.
# Allocates core networking and computing (e.g. GPU instances) if required.

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "visionquery-vpc"
    Environment = var.environment
  }
}
