# Phase 1 — Terraform: GCP + Cloud SQL

Provisions a Cloud SQL PostgreSQL 15 instance on GCP for ResearchLineage.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Terraform | ≥ 1.5 | `terraform version` |
| gcloud CLI | any | `gcloud version` |
| GCP project | exists | GCP Console |

### GCP auth
```bash
gcloud auth application-default login
gcloud config set project researchlineage
```

Ensure your account has these roles on the project:
- `roles/cloudsql.admin`
- `roles/serviceusage.serviceUsageAdmin`
- `roles/compute.networkAdmin` (for VPC/networking)

---

## Setup

### 1. Copy and fill in variables
```bash
cp terraform.tfvars.template terraform.tfvars
# Edit terraform.tfvars — at minimum set db_password
```

### 2. Add your IP (optional but recommended)
Edit `terraform.tfvars`:
```hcl
authorized_networks = [
  { name = "my-workstation", value = "203.0.113.42/32" }
]
```
Find your IP: `curl -4 ifconfig.me`

### 3. Initialize Terraform
```bash
terraform init
```

### 4. Preview changes
```bash
terraform plan
```
Review the output. You should see ~4 resources to create.

### 5. Apply
```bash
terraform apply
```
Type `yes` when prompted. Provisioning takes ~5–10 minutes.

### 6. Capture outputs
```bash
terraform output
```
Save the `public_ip` and `connection_name` — you'll need them for Phase 2.

---

## Connecting to the Database

### Option A — Direct connection (IP must be in authorized_networks)
```bash
psql "postgresql://rl_user:<password>@<public_ip>:5432/researchlineage"
```

### Option B — Cloud SQL Auth Proxy (recommended for production)
```bash
# Install proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.9.0/cloud-sql-proxy.darwin.arm64
chmod +x cloud-sql-proxy

# Run proxy (use connection_name from terraform output)
./cloud-sql-proxy <connection_name> --port 5432

# Connect via localhost
psql "postgresql://rl_user:<password>@127.0.0.1:5432/researchlineage"
```

---

## Tear Down

```bash
terraform destroy
```

> If `deletion_protection = true`, first set it to `false` and `terraform apply`, then destroy.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Error 403: Cloud SQL Admin API not enabled` | Wait 30s after `terraform apply` and retry, or enable manually in GCP Console |
| `Error creating instance: already exists` | Change `instance_name` in tfvars or import the existing instance |
| `Connection refused` | Check `authorized_networks` includes your IP, or use Auth Proxy |
| `FATAL: password authentication failed` | Verify `db_password` in tfvars matches what you're using in psql |
| `googleapi: Error 409` | Instance name was recently deleted — GCP recycles names; wait ~1 week or use a new name |

---

## What's Created

| Resource | Description |
|----------|-------------|
| `google_project_service.sqladmin` | Enables Cloud SQL Admin API |
| `google_project_service.compute` | Enables Compute Engine API |
| `google_project_service.servicenetworking` | Enables Service Networking API |
| `google_sql_database_instance.main` | PostgreSQL 15 instance on `db-f1-micro` |
| `google_sql_database.main` | `researchlineage` database |
| `google_sql_user.main` | `rl_user` database user |

---

## Next Steps → Phase 2

After `terraform apply` completes:

1. Run `terraform output` and copy the `public_ip`
2. Go to `../postgres/schema/`
3. Edit `deploy_schema.sh` — set `DB_URL` to the output connection string
4. Run `./deploy_schema.sh` to apply the schema
