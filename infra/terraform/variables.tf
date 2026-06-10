variable "aws_region" {
  description = "Target AWS Region"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Target Deployment Environment"
  type        = string
  default     = "development"
}
