# Mimir Backend Infrastructure
# GCP Compute Engine - All-in-one (API + DB + RabbitMQ in Docker)

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-northeast3"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "asia-northeast3-a"
}

variable "machine_type" {
  description = "VM Machine Type"
  type        = string
  default     = "e2-medium"  # 2 vCPU, 4GB RAM - Docker needs more memory
}

variable "github_repo" {
  description = "GitHub repository URL (must be public)"
  type        = string
  default     = "https://github.com/karl21-02/ora-automation.git"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
  default     = "mimir_secret_password"
}

variable "gemini_api_key" {
  description = "Google Gemini API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_cloud_project_id" {
  description = "GCP Project ID for Gemini"
  type        = string
  default     = ""
}

# Network
resource "google_compute_network" "mimir_network" {
  name                    = "mimir-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "mimir_subnet" {
  name          = "mimir-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.mimir_network.id
}

# Firewall Rules
resource "google_compute_firewall" "allow_http" {
  name    = "mimir-allow-http"
  network = google_compute_network.mimir_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["mimir-backend"]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "mimir-allow-ssh"
  network = google_compute_network.mimir_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["mimir-backend"]
}

# Static IP
resource "google_compute_address" "mimir_ip" {
  name   = "mimir-backend-ip"
  region = var.region
}

# Compute Engine Instance - All-in-one
resource "google_compute_instance" "mimir_backend" {
  name         = "mimir-backend"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["mimir-backend"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 50  # GB - need space for Docker images
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.mimir_subnet.id
    access_config {
      nat_ip = google_compute_address.mimir_ip.address
    }
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e
    exec > >(tee /var/log/startup-script.log) 2>&1

    echo "=== Starting Mimir Backend Setup ==="

    # Update system
    apt-get update
    apt-get install -y git

    # Install Docker
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker

    # Install Docker Compose v2
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    # Create app directory
    mkdir -p /opt/mimir
    cd /opt/mimir

    # Clone repository
    git clone ${var.github_repo} app
    cd app

    # Create production .env file
    cat > .env << ENVFILE
# Database
DATABASE_URL=postgresql://mimir:${var.db_password}@postgres:5432/mimir_db
POSTGRES_USER=mimir
POSTGRES_PASSWORD=${var.db_password}
POSTGRES_DB=mimir_db

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# Gemini
GOOGLE_CLOUD_PROJECT_ID=${var.google_cloud_project_id}
GOOGLE_CLOUD_LOCATION=asia-northeast3
GEMINI_MODEL=gemini-2.0-flash

# App settings
ORA_AUTOMATION_ROOT=/app
ORA_PROJECTS_ROOT=/workspace
ORCHESTRATION_PROFILE=standard
ENVFILE

    # Start services
    docker compose -f docker-compose.yml up -d

    echo "=== Mimir Backend Setup Complete ==="
    echo "API available at: http://$(curl -s ifconfig.me):8000"
  EOF

  service_account {
    scopes = ["cloud-platform"]
  }

  labels = {
    app = "mimir"
    env = "production"
  }

  # Allow time for startup script
  depends_on = [
    google_compute_firewall.allow_http,
    google_compute_firewall.allow_ssh
  ]
}

# Outputs
output "backend_ip" {
  description = "Backend server public IP"
  value       = google_compute_address.mimir_ip.address
}

output "api_url" {
  description = "API URL"
  value       = "http://${google_compute_address.mimir_ip.address}:8000"
}

output "health_check" {
  description = "Health check URL"
  value       = "http://${google_compute_address.mimir_ip.address}:8000/health"
}

output "ssh_command" {
  description = "SSH command"
  value       = "gcloud compute ssh mimir-backend --zone=${var.zone} --project=${var.project_id}"
}

output "logs_command" {
  description = "View startup logs"
  value       = "gcloud compute ssh mimir-backend --zone=${var.zone} --command='sudo cat /var/log/startup-script.log'"
}

output "docker_logs" {
  description = "View Docker logs"
  value       = "gcloud compute ssh mimir-backend --zone=${var.zone} --command='cd /opt/mimir/app && docker compose logs -f'"
}
