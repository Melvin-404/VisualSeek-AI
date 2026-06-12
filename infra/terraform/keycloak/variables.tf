variable "keycloak_url" {
  type        = string
  description = "URL of Keycloak server"
  default     = "http://localhost:8080"
}

variable "keycloak_admin_user" {
  type        = string
  description = "Keycloak admin user name"
  default     = "admin"
}

variable "keycloak_admin_password" {
  type        = string
  description = "Keycloak admin password"
  default     = "admin"
  sensitive   = true
}
