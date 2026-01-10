# Deployment Guide

## Overview

This guide covers deploying the Workflow Orchestrator in various environments: development, staging, and production.

## Prerequisites

- Python 3.9+
- pip
- Virtual environment tool (venv, virtualenv, or conda)
- (Optional) Docker
- (Optional) Kubernetes

## Quick Start (Development)

### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/your-org/workflow-orchestrator.git
cd workflow-orchestrator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
# Generate JWT secret
export ORCHESTRATOR_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')

# (Optional) Override default settings
export ORCHESTRATOR_SERVER_PORT=9000
export ORCHESTRATOR_LOG_LEVEL=DEBUG
```

### 3. Start Orchestrator

```bash
# Start API server
python -m uvicorn src.orchestrator.api:app --host localhost --port 8000

# Or use the convenience script
python -m src.orchestrator.api
```

### 4. Verify Deployment

```bash
# Check health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs
```

## Configuration

### Configuration Files

Create `orchestrator.yaml` in the working directory:

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  workers: 4
  timeout: 30

security:
  jwt_secret_env_var: "ORCHESTRATOR_JWT_SECRET"
  token_expiry_seconds: 7200
  require_token_rotation: true

state:
  state_file: ".orchestrator/state.json"
  auto_save: true
  checkpoint_interval: 60

event:
  max_history: 1000
  enable_event_persistence: false

audit:
  audit_file: ".orchestrator/audit.jsonl"
  max_entries: 100000
  auto_rotate: true
  rotate_size_mb: 100

logging:
  level: "INFO"
  format: "json"
  console: true
```

### Environment Variables

Override any configuration via environment variables:

```bash
# Server configuration
export ORCHESTRATOR_SERVER_PORT=9000
export ORCHESTRATOR_SERVER_HOST=0.0.0.0
export ORCHESTRATOR_SERVER_WORKERS=8

# Security
export ORCHESTRATOR_JWT_SECRET="your-secret-key-here"
export ORCHESTRATOR_SECURITY_TOKEN_EXPIRY_SECONDS=3600

# Logging
export ORCHESTRATOR_LOG_LEVEL=INFO
export ORCHESTRATOR_LOG_FILE=/var/log/orchestrator/api.log

# State management
export ORCHESTRATOR_STATE_FILE=/var/lib/orchestrator/state.json

# Audit logging
export ORCHESTRATOR_AUDIT_FILE=/var/log/orchestrator/audit.jsonl
```

### Configuration Priority

1. Environment variables (highest)
2. Configuration file
3. Defaults (lowest)

## Production Deployment

### Architecture

```
┌─────────────┐
│   Agents    │
│  (Multiple) │
└──────┬──────┘
       │
       v
┌──────────────┐      ┌──────────────┐
│   Load       │──────>│  Orchestrator │
│   Balancer   │      │   Instances   │
│   (nginx)    │      │   (Multiple)  │
└──────────────┘      └──────┬────────┘
                             │
                             v
                      ┌──────────────┐
                      │   Shared     │
                      │   Storage    │
                      │   (NFS/EFS)  │
                      └──────────────┘
```

### Requirements

**Hardware**:
- CPU: 4+ cores per instance
- RAM: 8GB+ per instance
- Disk: 100GB+ (for logs and state)

**Network**:
- Load balancer: 443/TCP (HTTPS)
- Orchestrator instances: 8000/TCP (internal)
- Shared storage: NFS or equivalent

### Setup Steps

#### 1. Prepare Environment

```bash
# Create service user
sudo useradd -r -s /bin/bash orchestrator

# Create directories
sudo mkdir -p /opt/orchestrator
sudo mkdir -p /var/lib/orchestrator
sudo mkdir -p /var/log/orchestrator
sudo mkdir -p /etc/orchestrator

# Set permissions
sudo chown -R orchestrator:orchestrator /opt/orchestrator
sudo chown -R orchestrator:orchestrator /var/lib/orchestrator
sudo chown -R orchestrator:orchestrator /var/log/orchestrator
```

#### 2. Install Application

```bash
# Switch to orchestrator user
sudo -u orchestrator bash

# Clone and install
cd /opt/orchestrator
git clone https://github.com/your-org/workflow-orchestrator.git .
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

#### 3. Configure Application

```bash
# Create production config
sudo -u orchestrator cat > /etc/orchestrator/orchestrator.yaml << 'EOF'
server:
  host: "0.0.0.0"
  port: 8000
  workers: 8
  timeout: 60

security:
  jwt_secret_env_var: "ORCHESTRATOR_JWT_SECRET"
  token_expiry_seconds: 7200
  require_token_rotation: true

state:
  state_file: "/var/lib/orchestrator/state.json"
  auto_save: true
  checkpoint_interval: 60

audit:
  audit_file: "/var/log/orchestrator/audit.jsonl"
  max_entries: 1000000
  auto_rotate: true
  rotate_size_mb: 500

logging:
  level: "INFO"
  format: "json"
  file: "/var/log/orchestrator/api.log"
  console: false
EOF

# Set JWT secret (use secrets manager in production!)
echo "ORCHESTRATOR_JWT_SECRET=$(openssl rand -hex 32)" | \
  sudo tee /etc/orchestrator/env > /dev/null
sudo chmod 600 /etc/orchestrator/env
```

#### 4. Create Systemd Service

```bash
sudo cat > /etc/systemd/system/orchestrator.service << 'EOF'
[Unit]
Description=Workflow Orchestrator API
After=network.target

[Service]
Type=notify
User=orchestrator
Group=orchestrator
WorkingDirectory=/opt/orchestrator
Environment="PATH=/opt/orchestrator/venv/bin"
EnvironmentFile=/etc/orchestrator/env
ExecStart=/opt/orchestrator/venv/bin/uvicorn \
  src.orchestrator.api:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 8 \
  --log-config /etc/orchestrator/logging.json

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=0

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/orchestrator /var/log/orchestrator

[Install]
WantedBy=multi-user.target
EOF
```

#### 5. Start Service

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable orchestrator
sudo systemctl start orchestrator

# Check status
sudo systemctl status orchestrator

# View logs
sudo journalctl -u orchestrator -f
```

### Load Balancer (nginx)

```nginx
upstream orchestrator {
    least_conn;
    server orchestrator-1.internal:8000 max_fails=3 fail_timeout=30s;
    server orchestrator-2.internal:8000 max_fails=3 fail_timeout=30s;
    server orchestrator-3.internal:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name orchestrator.example.com;

    ssl_certificate /etc/ssl/certs/orchestrator.crt;
    ssl_certificate_key /etc/ssl/private/orchestrator.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Proxy settings
    location / {
        proxy_pass http://orchestrator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Health check endpoint
    location /health {
        proxy_pass http://orchestrator/health;
        access_log off;
    }
}
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .
RUN pip install -e .

# Create directories
RUN mkdir -p /var/lib/orchestrator /var/log/orchestrator

# Expose port
EXPOSE 8000

# Run as non-root
RUN useradd -r -u 1000 orchestrator && \
    chown -R orchestrator:orchestrator /app /var/lib/orchestrator /var/log/orchestrator
USER orchestrator

# Start application
CMD ["uvicorn", "src.orchestrator.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  orchestrator:
    build: .
    image: orchestrator:latest
    ports:
      - "8000:8000"
    environment:
      - ORCHESTRATOR_JWT_SECRET=${ORCHESTRATOR_JWT_SECRET}
      - ORCHESTRATOR_SERVER_WORKERS=4
      - ORCHESTRATOR_LOG_LEVEL=INFO
    volumes:
      - ./data:/var/lib/orchestrator
      - ./logs:/var/log/orchestrator
      - ./workflows:/app/workflows:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Optional: Redis for shared state
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

### Build and Run

```bash
# Build image
docker build -t orchestrator:latest .

# Generate secret
export ORCHESTRATOR_JWT_SECRET=$(openssl rand -hex 32)

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f orchestrator

# Scale instances
docker-compose up -d --scale orchestrator=3
```

## Kubernetes Deployment

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orchestrator
```

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orchestrator-config
  namespace: orchestrator
data:
  orchestrator.yaml: |
    server:
      host: "0.0.0.0"
      port: 8000
      workers: 4
    security:
      jwt_secret_env_var: "ORCHESTRATOR_JWT_SECRET"
      token_expiry_seconds: 7200
    logging:
      level: "INFO"
      format: "json"
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: orchestrator-secrets
  namespace: orchestrator
type: Opaque
data:
  jwt-secret: <base64-encoded-secret>
```

```bash
# Create secret
kubectl create secret generic orchestrator-secrets \
  --from-literal=jwt-secret=$(openssl rand -hex 32) \
  -n orchestrator
```

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator
  namespace: orchestrator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: orchestrator
        image: orchestrator:latest
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ORCHESTRATOR_JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: orchestrator-secrets
              key: jwt-secret
        volumeMounts:
        - name: config
          mountPath: /etc/orchestrator
        - name: state
          mountPath: /var/lib/orchestrator
        - name: logs
          mountPath: /var/log/orchestrator
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: config
        configMap:
          name: orchestrator-config
      - name: state
        persistentVolumeClaim:
          claimName: orchestrator-state
      - name: logs
        emptyDir: {}
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orchestrator
  namespace: orchestrator
spec:
  selector:
    app: orchestrator
  ports:
  - port: 80
    targetPort: 8000
    name: http
  type: ClusterIP
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orchestrator
  namespace: orchestrator
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - orchestrator.example.com
    secretName: orchestrator-tls
  rules:
  - host: orchestrator.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: orchestrator
            port:
              number: 80
```

### Deploy

```bash
# Apply all resources
kubectl apply -f k8s/

# Check status
kubectl get pods -n orchestrator
kubectl logs -f -n orchestrator -l app=orchestrator

# Scale deployment
kubectl scale deployment orchestrator --replicas=5 -n orchestrator
```

## Monitoring

### Health Checks

```bash
# Basic health
curl http://localhost:8000/health

# Detailed status
curl http://localhost:8000/ | jq
```

### Metrics

Add Prometheus metrics:

```python
# Add to src/orchestrator/api.py
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

request_count = Counter('http_requests_total', 'Total HTTP requests')
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### Logging

View logs:

```bash
# Systemd
sudo journalctl -u orchestrator -f

# Docker
docker logs -f orchestrator

# Kubernetes
kubectl logs -f -n orchestrator -l app=orchestrator
```

### Alerting

Example Prometheus alerts:

```yaml
groups:
- name: orchestrator
  rules:
  - alert: OrchestratorDown
    expr: up{job="orchestrator"} == 0
    for: 5m
    annotations:
      summary: "Orchestrator instance down"

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    annotations:
      summary: "High error rate detected"
```

## Security

### TLS/SSL

Always use HTTPS in production:

```bash
# Generate self-signed cert (development only)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Production: Use Let's Encrypt or your CA
```

### JWT Secrets

**Critical**: Use strong, unique secrets:

```bash
# Generate strong secret
openssl rand -hex 32

# Rotate regularly (every 90 days)
```

### Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 443/tcp  # HTTPS
sudo ufw deny 8000/tcp  # Block direct access
sudo ufw enable
```

### Rate Limiting

Add rate limiting to nginx:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20;
    proxy_pass http://orchestrator;
}
```

## Backup and Recovery

### State Backup

```bash
# Backup state file
tar -czf orchestrator-state-$(date +%Y%m%d).tar.gz \
  /var/lib/orchestrator/state.json

# Upload to S3
aws s3 cp orchestrator-state-$(date +%Y%m%d).tar.gz \
  s3://backups/orchestrator/
```

### Automated Backups

```bash
# Add to crontab
0 2 * * * /usr/local/bin/backup-orchestrator.sh
```

### Recovery

```bash
# Download backup
aws s3 cp s3://backups/orchestrator/orchestrator-state-20261111.tar.gz .

# Extract
tar -xzf orchestrator-state-20261111.tar.gz -C /var/lib/orchestrator/

# Restart service
sudo systemctl restart orchestrator
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u orchestrator -n 50

# Common issues:
# - JWT secret not set
# - Port already in use
# - Permission issues
```

### High Memory Usage

```bash
# Check memory
ps aux | grep orchestrator

# Reduce workers if needed
export ORCHESTRATOR_SERVER_WORKERS=2
```

### Slow Response Times

```bash
# Check system resources
top
df -h

# Review logs for slow queries
grep "duration" /var/log/orchestrator/api.log
```

## Performance Tuning

### Worker Processes

```yaml
server:
  workers: $((CPU_CORES * 2 + 1))
```

### Database Connection Pool

If using external database:

```yaml
database:
  pool_size: 20
  max_overflow: 10
  pool_timeout: 30
```

### Caching

Add Redis caching:

```python
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)
```

## See Also

- [Agent SDK Guide](AGENT_SDK_GUIDE.md)
- [Workflow YAML Specification](WORKFLOW_SPEC.md)
- [Security Best Practices](SECURITY.md)
