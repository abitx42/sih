# Truth Lens : Oracle Cloud Always Free Deployment Guide

**Target Platform:** Oracle Cloud Infrastructure (OCI) Always Free Compute Instance  
**OS:** Ubuntu 22.04 LTS / 24.04 LTS  
**Application:** Truth Lens — Digital Evidence Forensics Platform (SIH PS-27)  

---

## 🏛️ 1. Architecture & Prototype Boundaries

Truth Lens is containerized as a self-contained, single-service forensic analysis node:
- **FastAPI Backend + HTML5/CSS3/JS Forensic Console**
- **In-Process Python ML Inference** (`dima806/deepfake_vs_real_image_detection` via PyTorch)
- **Local SQLite Database & File Storage** (`./storage/` mounted as a persistent Docker volume)
- **Single Worker Policy**: Runs with `--workers 1` because SQLite and in-process `BackgroundTasks` are single-node prototype designs suitable for hackathon evaluations and lab triage.

> [!WARNING]
> **Prototype Demonstration Notice:**  
> This deployment is designed for hackathon evaluation and demonstration. Do **not** upload real classified or sensitive personal evidence to a public test instance.

---

## ☁️ 2. Step 1: Create an Oracle Cloud Always Free VM

1. Log in to the [Oracle Cloud Console](https://cloud.oracle.com/).
2. Navigate to **Compute** → **Instances** → Click **Create Instance**.
3. Configure the instance:
   - **Name:** `truth-lens-demo`
   - **Image:** **Canonical Ubuntu 22.04** or **Ubuntu 24.04 Minimal**
   - **Shape:** 
     - *Option A (Best Performance):* **Ampere A1 Flex (ARM)** with 2–4 OCPUs and 12–24 GB RAM (Always Free eligible).
     - *Option B (Standard):* **VM.Standard.E2.1.Micro (x86_64)** (1 OCPU, 1 GB RAM — Note: image model inference will be slower).
   - **Networking:** Select your Virtual Cloud Network (VCN) and ensure **"Assign a public IPv4 address"** is checked.
   - **SSH Keys:** Save the generated private key (`.key`) to your computer or upload your existing public key.
4. Click **Create** and wait for the instance state to become **RUNNING**.
5. Note your instance's **Public IP Address** (e.g. `129.153.x.x`).

---

## 🛡️ 3. Step 2: Configure Oracle Cloud & Host Firewall Rules

### A. Oracle Cloud VCN Ingress Rules (Web Console)
You must permit incoming traffic on ports **22 (SSH)**, **80 (HTTP)**, and **443 (HTTPS)**:
1. In Oracle Cloud Console, go to **Networking** → **Virtual Cloud Networks**.
2. Click your VCN → Click **Security Lists** → Click **Default Security List for `<vcn-name>`**.
3. Under **Ingress Rules**, click **Add Ingress Rules** and add:

| Source CIDR | IP Protocol | Destination Port Range | Description |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `22` | SSH Administration (Default) |
| `0.0.0.0/0` | TCP | `80` | HTTP Web Traffic (Truth Lens) |
| `0.0.0.0/0` | TCP | `443` | HTTPS Traffic |
| `0.0.0.0/0` | TCP | `8000` | Optional Alt HTTP Port |

### B. Ubuntu Host Firewall (`iptables` / `ufw`)
Oracle Cloud Ubuntu images include strict default `iptables` rules that block external ports. SSH into your VM and open ports 80 and 8000:

```bash
# Connect to your VM
ssh -i /path/to/your_private_key.key ubuntu@<YOUR_ORACLE_PUBLIC_IP>

# Open ports in iptables
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT

# Make iptables rules persistent across reboots
sudo apt-get update && sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

---

## 🐳 4. Step 3: Install Docker & Docker Compose on Ubuntu

Run the following commands on your Ubuntu instance to install official Docker:

```bash
# 1. Install prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

# 2. Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 3. Set up the Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Install Docker Engine, CLI, and Compose Plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 5. Allow running docker without sudo
sudo usermod -aG docker $USER
newgrp docker
```

---

## 🚀 5. Step 4: Clone Repository & Configure Environment

```bash
# 1. Clone repository from GitHub
git clone https://github.com/abitx42/sih.git
cd sih

# 2. Create environment file from example template
cp .env.example .env

# 3. (Optional) Edit .env if you have a TCET CoE Gateway / Qwen API key
nano .env
```

> [!NOTE]
> `LLM_API_KEY` is optional. If left blank, Truth Lens automatically uses its built-in offline deterministic NLG engine for AI explanations and Copilot Q&A.

---

## ⚡ 6. Step 5: Build and Run Truth Lens Container

```bash
# Build Docker image and start container in detached background mode
docker compose up -d --build
```

Verify the container is running and healthy:
```bash
docker compose ps
docker compose logs -f
```

---

## 🧠 7. Step 6: Pre-Warm ML Model & Seed Demo Exhibits

To ensure instantaneous inference and populate sample exhibits for evaluators:

```bash
# 1. Download and cache Hugging Face Vision Transformer weights into persistent storage
docker compose exec truth-lens python scripts/download_model.py

# 2. Seed multi-modal demo exhibits (Authentic & Spliced Image, Audio WAV, Document PDF, ZIP Archive, Video MP4)
docker compose exec truth-lens python scripts/seed_demo_data.py
```

---

## 🌐 8. Step 7: Verify Public Access

1. **Health Check via CLI:**
   ```bash
   curl -i http://localhost/health
   # Returns: HTTP 200 OK {"status": "HEALTHY", "service": "Truth Lens", ...}
   ```

2. **Open in Web Browser:**
   Navigate in your laptop or smartphone browser to:  
   👉 **`http://<YOUR_ORACLE_PUBLIC_IP>`**

---

## 🔄 9. Step 8: Updating the Deployment (`git pull`)

Whenever you push new code changes or bug fixes to GitHub `main`:

```bash
cd ~/sih

# Pull latest commits
git pull origin main

# Rebuild container with zero database data loss (storage is mounted on host)
docker compose up -d --build

# Confirm container health
docker compose ps
```

---

## 🧹 10. Useful Management Commands

| Action | Command |
|---|---|
| **View Live Logs** | `docker compose logs -f` |
| **Restart Service** | `docker compose restart` |
| **Stop Container** | `docker compose down` |
| **Run Rehearsal Check Inside Container** | `docker compose exec truth-lens python scripts/verify_demo_rehearsal.py` |
| **Run Pytest Suite Inside Container** | `docker compose exec truth-lens pytest -v -m "not slow"` |
| **Inspect Storage Directory** | `ls -la ./storage` |
