# ── Cloud SQL Instance ────────────────────────────────────────────────────────

resource "google_sql_database_instance" "main" {
  name             = var.instance_name
  database_version = var.postgres_version
  region           = var.region

  deletion_protection = var.deletion_protection

  settings {
    tier      = var.instance_tier
    disk_size = var.disk_size_gb
    disk_type = "PD_SSD"

    # ── Backups ───────────────────────────────────────────────────────────────
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"   # UTC — runs nightly at 3 AM
      point_in_time_recovery_enabled = false      # requires POSTGRES_15 Enterprise tier
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = var.backup_retention_days
        retention_unit   = "COUNT"
      }
    }

    # ── Maintenance window (Sunday 04:00 UTC) ─────────────────────────────────
    maintenance_window {
      day          = 1   # Sunday (1 = Monday in GCP API, actually use 1=Mon … 7=Sun; Sunday = 7)
      hour         = 4
      update_track = "stable"
    }

    # ── Network / IP ──────────────────────────────────────────────────────────
    ip_configuration {
      ipv4_enabled = true   # Public IP

      dynamic "authorized_networks" {
        for_each = var.authorized_networks
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.value
        }
      }
    }

    # ── Database flags ────────────────────────────────────────────────────────
    database_flags {
      name  = "max_connections"
      value = "100"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"   # log queries taking > 1 second
    }
  }

  depends_on = [
    google_project_service.sqladmin,
    google_project_service.compute,
  ]
}

# ── Database ──────────────────────────────────────────────────────────────────

resource "google_sql_database" "main" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

# ── Database User ─────────────────────────────────────────────────────────────

resource "google_sql_user" "main" {
  name     = var.db_user
  instance = google_sql_database_instance.main.name
  password = var.db_password
}
