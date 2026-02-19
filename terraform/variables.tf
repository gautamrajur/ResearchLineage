variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "researchlineage"
}

variable "region" {
  description = "GCP region for Cloud SQL and other resources"
  type        = string
  default     = "us-central1"
}

variable "postgres_version" {
  description = "PostgreSQL major version for Cloud SQL"
  type        = string
  default     = "POSTGRES_15"
}

variable "instance_tier" {
  description = "Cloud SQL machine tier (e.g. db-f1-micro, db-g1-small, db-n1-standard-2)"
  type        = string
  default     = "db-f1-micro"
}

variable "instance_name" {
  description = "Name of the Cloud SQL instance"
  type        = string
  default     = "researchlineage-db"
}

variable "db_name" {
  description = "Name of the PostgreSQL database to create"
  type        = string
  default     = "researchlineage"
}

variable "db_user" {
  description = "PostgreSQL user name"
  type        = string
  default     = "rl_user"
}

variable "db_password" {
  description = "PostgreSQL user password (set via terraform.tfvars or TF_VAR_db_password env var)"
  type        = string
  sensitive   = true
}

variable "authorized_networks" {
  description = "List of CIDR ranges allowed to connect to the public IP. Add your IP here."
  type = list(object({
    name  = string
    value = string
  }))
  default = [
    # Example: { name = "my-home", value = "203.0.113.0/32" }
    # Leave empty to block all external access (connect via Cloud Shell or Cloud SQL Auth Proxy)
  ]
}

variable "backup_retention_days" {
  description = "Number of daily backups to retain"
  type        = number
  default     = 7
}

variable "disk_size_gb" {
  description = "Initial disk size in GB (minimum 10)"
  type        = number
  default     = 10
}

variable "deletion_protection" {
  description = "Prevent accidental Terraform deletion of the instance. Set false for dev/test."
  type        = bool
  default     = false
}
