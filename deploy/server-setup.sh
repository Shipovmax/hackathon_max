#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server: Docker, Compose, git and 2 GB of swap.
# Run as a regular user with sudo, then log out and back in so the docker group applies.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo apt-get install -y docker-buildx || true

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

if [ -z "$(swapon --show)" ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "Done. Log out and log in again, then continue with the README section 'Деплой на сервер'."
