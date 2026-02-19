output "instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.main.name
}

output "connection_name" {
  description = "Cloud SQL connection name — used with Cloud SQL Auth Proxy (project:region:instance)"
  value       = google_sql_database_instance.main.connection_name
}

output "public_ip" {
  description = "Public IP address of the Cloud SQL instance"
  value       = google_sql_database_instance.main.public_ip_address
}

output "database_name" {
  description = "Name of the created database"
  value       = google_sql_database.main.name
}

output "database_user" {
  description = "Database user name"
  value       = google_sql_user.main.name
}

output "database_url" {
  description = "PostgreSQL connection URL (password redacted — substitute manually)"
  value       = "postgresql://${google_sql_user.main.name}:<PASSWORD>@${google_sql_database_instance.main.public_ip_address}:5432/${google_sql_database.main.name}"
  sensitive   = false
}

output "phase2_connection_hint" {
  description = "Copy this into your Phase 2 deploy_schema.sh DB_URL variable"
  value       = "postgresql://${google_sql_user.main.name}:<PASSWORD>@${google_sql_database_instance.main.public_ip_address}:5432/${google_sql_database.main.name}"
}
