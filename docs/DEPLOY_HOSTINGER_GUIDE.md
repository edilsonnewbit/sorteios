# Guia de Deploy Sorteios no Hostinger
**Domínio:** `sorteio.overflowmvmt.com`

---

## 1. Pré-requisitos

### 1.1 Hostinger VPS
- [ ] VPS criada e com IP fixo atribuído
- [ ] Ubuntu 22.04 LTS (ou similar)
- [ ] SSH acesso configurado
- [ ] Docker + Docker Compose instalados
- [ ] 2GB RAM mínimo, 10GB disco livre

### 1.2 DNS
- [ ] Domínio `sorteio.overflowmvmt.com` apontando para IP da VPS
- [ ] Propagação DNS confirmada (até 48h)

### 1.3 GitHub
- [ ] Repositório públicizado ou com acesso SSH configurado
- [ ] Webhook SSH para auto-deploy (opcional)

---

## 2. Preparação: Estrutura de Diretórios

### 2.1 Conectar na VPS
```bash
ssh root@<IP_DA_VPS>
```

### 2.2 Criar diretório de produção
```bash
mkdir -p /opt/apps/sorteios
cd /opt/apps/sorteios
git init --bare repo.git
cat > repo.git/hooks/post-receive << 'EOF'
#!/bin/bash
cd /opt/apps/sorteios/sorteios-prod
git fetch origin main
git reset --hard origin/main
docker compose down
docker compose up --build -d
EOF
chmod +x repo.git/hooks/post-receive
```

### 2.3 Clone inicial
```bash
cd /opt/apps/sorteios
git clone /opt/apps/sorteios/repo.git sorteios-prod
cd sorteios-prod
```

---

## 3. Configuração de Ambiente

### 3.1 Arquivo `.env.production`
Criar em `/opt/apps/sorteios/sorteios-prod/.env.production`:

```bash
# Database (usar PostgreSQL em produção, nunca SQLite)
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/sorteios

# Proxy / Reverse Proxy
ALLOWED_HOSTS=sorteio.overflowmvmt.com,localhost
CORS_ORIGINS=https://sorteio.overflowmvmt.com

# Logging
LOG_LEVEL=info

# FastAPI
ENVIRONMENT=production
DEBUG=False

# Session
SESSION_SECRET=${SESSION_SECRET}  # Gerado: openssl rand -hex 32

# Admin API (opcional, para integração futura)
ADMIN_API_KEY=${ADMIN_API_KEY}  # Gerado: openssl rand -hex 32

# Uploads (diretório persistente)
UPLOAD_DIR=/data/uploads
```

### 3.2 Arquivo `docker-compose.prod.yml`
Criar em `/opt/apps/sorteios/sorteios-prod/docker-compose.prod.yml`:

```yaml
services:
  web:
    build: .
    restart: always
    ports:
      - "127.0.0.1:8000:8000"  # Expor apenas em localhost (reverse proxy na frente)
    environment:
      DATABASE_URL: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/sorteios"
      LOG_LEVEL: "info"
      SESSION_SECRET: "${SESSION_SECRET}"
      ADMIN_API_KEY: "${ADMIN_API_KEY}"
      ENVIRONMENT: "production"
      DEBUG: "False"
    volumes:
      - sorteios_data:/data
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_USER: "${POSTGRES_USER}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
      POSTGRES_DB: sorteios
    volumes:
      - sorteios_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  sorteios_data: {}
  sorteios_pgdata: {}
```

---

## 4. Configuração de Secrets no GitHub

### 4.1 Acessar GitHub Repository Settings
1. Ir a **Settings > Secrets and variables > Actions**
2. Adicionar os seguintes **Repository Secrets**:

| Secret | Valor | Descrição |
|--------|-------|-----------|
| `HOSTINGER_VM_ID` | `<VM_ID>` | ID da VPS na Hostinger (encontrar em Hostinger Dashboard) |
| `HOSTINGER_API_KEY` | `<API_KEY>` | API Key gerada em Hostinger |
| `VPS_HOST` | `<IP_VPS>` | IP da VPS |
| `VPS_USER` | `root` | Usuário SSH (geralmente root) |
| `VPS_SSH_PRIVATE_KEY` | `<PRIVATE_KEY>` | Chave SSH privada (output de `cat ~/.ssh/id_rsa` local) |
| `POSTGRES_USER` | `sorteios_admin` | Usuário PostgreSQL |
| `POSTGRES_PASSWORD` | `<STRONG_PASSWORD>` | Senha do PostgreSQL (mín. 24 chars) — gerar com `openssl rand -base64 24` |
| `SESSION_SECRET` | `<SECRET>` | Secret para sessões — gerar com `openssl rand -hex 32` |
| `ADMIN_API_KEY` | `<API_KEY>` | Chave API admin — gerar com `openssl rand -hex 32` |

### 4.2 Gerar Secrets Seguros (local)
```bash
# PostgreSQL Password
openssl rand -base64 24

# Session Secret
openssl rand -hex 32

# Admin API Key
openssl rand -hex 32

# SSH Private Key (copiar output de):
cat ~/.ssh/id_rsa
```

---

## 5. Setup SSL/TLS com Let's Encrypt

### 5.1 Conectar via SSH e instalar Certbot
```bash
ssh root@<IP_VPS>
apt-get update && apt-get install -y certbot python3-certbot-nginx
```

### 5.2 Criar Script de Inicialização SSL
Criar `/opt/apps/sorteios/init-ssl.sh`:

```bash
#!/bin/bash
set -e

DOMAIN="sorteio.overflowmvmt.com"
EMAIL="admin@overflowmvmt.com"
CERT_DIR="/opt/apps/sorteios/certs"

mkdir -p $CERT_DIR

# Gerar certificado Let's Encrypt
certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email $EMAIL \
  -d $DOMAIN

# Copiar para diretório da app
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $CERT_DIR/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $CERT_DIR/

# Criar renewal hook (auto-restart Docker)
cat > /etc/letsencrypt/renewal-hooks/post/docker-restart.sh << 'HOOK'
#!/bin/bash
cd /opt/apps/sorteios/sorteios-prod
docker compose -f docker-compose.prod.yml restart nginx || true
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/post/docker-restart.sh

echo "✓ SSL configurado para $DOMAIN"
```

### 5.3 Executar Setup SSL (primeira vez apenas)
```bash
ssh root@<IP_VPS>
bash /opt/apps/sorteios/init-ssl.sh
```

---

## 6. Configurar Reverse Proxy (Nginx)

### 6.1 Adicionar serviço Nginx ao `docker-compose.prod.yml`
```yaml
  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - web
```

### 6.2 Criar `nginx.conf`
```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    gzip on;

    # Redirecionar HTTP → HTTPS
    server {
        listen 80;
        server_name sorteio.overflowmvmt.com;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS
    server {
        listen 443 ssl http2;
        server_name sorteio.overflowmvmt.com;

        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        client_max_body_size 50M;

        # Proxy para FastAPI
        location / {
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect off;
            
            # WebSocket (se necessário)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # Health check (sem logs)
        location /health {
            access_log off;
            proxy_pass http://web:8000/health;
        }
    }
}
```

---

## 7. Deployment Manual (Primeira Vez)

### 7.1 No VPS
```bash
cd /opt/apps/sorteios/sorteios-prod

# Copiar arquivo de environment
cat > .env.production << 'EOF'
DATABASE_URL=postgresql://sorteios_admin:<PASSWORD>@db:5432/sorteios
POSTGRES_USER=sorteios_admin
POSTGRES_PASSWORD=<PASSWORD>
SESSION_SECRET=<SESSION_SECRET>
ADMIN_API_KEY=<ADMIN_API_KEY>
LOG_LEVEL=info
ENVIRONMENT=production
EOF

# Iniciar containers
docker compose -f docker-compose.prod.yml up -d

# Aguardar saúde → verificar logs
docker compose -f docker-compose.prod.yml logs -f web

# Quando pronto (exit code 0), validar:
curl -k https://sorteio.overflowmvmt.com/health
```

### 7.2 Esperado
Resposta HTTP 200:
```json
{"status": "ok", "version": "..."}
```

---

## 8. Configurar Auto-Deploy (GitHub Actions)

### 8.1 Criar Workflow
Criar `.github/workflows/deploy-prod.yml`:

```yaml
name: Deploy Sorteios - Produção

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Hostinger VPS
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_PRIVATE_KEY }}
          script: |
            cd /opt/apps/sorteios/sorteios-prod
            git fetch origin main
            git reset --hard origin/main
            
            # Atualizar .env
            cat > .env.production << EOF
            DATABASE_URL=postgresql://${{ secrets.POSTGRES_USER }}:${{ secrets.POSTGRES_PASSWORD }}@db:5432/sorteios
            POSTGRES_USER=${{ secrets.POSTGRES_USER }}
            POSTGRES_PASSWORD=${{ secrets.POSTGRES_PASSWORD }}
            SESSION_SECRET=${{ secrets.SESSION_SECRET }}
            ADMIN_API_KEY=${{ secrets.ADMIN_API_KEY }}
            LOG_LEVEL=info
            ENVIRONMENT=production
            EOF
            
            # Rebuild e reiniciar
            docker compose -f docker-compose.prod.yml down
            docker compose -f docker-compose.prod.yml up --build -d
            
            # Health check
            sleep 15
            curl -f -k https://sorteio.overflowmvmt.com/health || exit 1
```

### 8.2 Adicionar secrets ao GitHub (já feito em seção 4)

---

## 9. Operações Pós-Deploy

### 9.1 Health Check
```bash
# Local ou via GitHub Actions:
curl -k https://sorteio.overflowmvmt.com/health

# Esperado:
# HTTP 200 - {"status": "ok"}
```

### 9.2 Visualizar Logs
```bash
ssh root@<IP_VPS>
cd /opt/apps/sorteios/sorteios-prod

# Logs web
docker compose -f docker-compose.prod.yml logs -f web

# Logs database
docker compose -f docker-compose.prod.yml logs -f db

# Todos
docker compose -f docker-compose.prod.yml logs -f
```

### 9.3 Parar / Iniciar / Reiniciar
```bash
# Parar
docker compose -f docker-compose.prod.yml down

# Iniciar
docker compose -f docker-compose.prod.yml up -d

# Reiniciar
docker compose -f docker-compose.prod.yml restart web
```

### 9.4 Backup de Dados
```bash
# Backup PostgreSQL
docker compose -f docker-compose.prod.yml exec db pg_dump -U sorteios_admin sorteios > sorteios_backup_$(date +%Y%m%d_%H%M%S).sql

# Backup uploads
tar -czf sorteios_uploads_$(date +%Y%m%d_%H%M%S).tar.gz /opt/apps/sorteios/sorteios-prod/data/uploads
```

---

## 10. Renovação de Certificado SSL

### 10.1 Auto-renew com Cron (já configurado acima)
Let's Encrypt certificados expiram em 90 dias.  
Certbot configura auto-renew automaticamente.

### 10.2 Verificar Status
```bash
ssh root@<IP_VPS>
certbot renew --dry-run
```

---

## 11. Troubleshooting

| Problema | Solução |
|----------|---------|
| **502 Bad Gateway** | `docker compose -f docker-compose.prod.yml logs web` — verificar erro na app |
| **SSL certificate not trusted** | Aguardar propagação DNS + Let's Encrypt reconhecimento |
| **Conexão recusada na porta 8000** | Verificar que Nginx está rodando: `docker compose -f docker-compose.prod.yml logs nginx` |
| **"Connection refused" via SSH** | Verificar firewall VPS: porta 22 liberada + SSH ativo |
| **Banco de dados não conecta** | Verificar `POSTGRES_PASSWORD` está correto em `.env.production` vs Docker Compose |

---

## 12. Checklist Final

- [ ] VPS criada e acessível via SSH
- [ ] Docker + Docker Compose instalados no VPS
- [ ] DNS `sorteio.overflowmvmt.com` → IP VPS confirmado
- [ ] Secrets adicionados ao GitHub (seção 4)
- [ ] `.env.production` criado no VPS
- [ ] `docker-compose.prod.yml` criado
- [ ] `nginx.conf` criado
- [ ] SSL/TLS iniciado com `init-ssl.sh`
- [ ] Deploy manual testado e validado
- [ ] GitHub Actions workflow criado
- [ ] Health check respondendo
- [ ] Logs monitorados (sem erros críticos)
- [ ] Backup automático configurado (opcional)

---

## 13. Contato e Suporte

Para dúvidas técnicas:
- Docs FastAPI: https://fastapi.tiangolo.com
- Docker Compose: https://docs.docker.com/compose
- Let's Encrypt: https://letsencrypt.org/docs

---

**Última atualização:** 2026-05-01 BRT  
**Versão:** 1.0  
**Autor:** GitHub Copilot
