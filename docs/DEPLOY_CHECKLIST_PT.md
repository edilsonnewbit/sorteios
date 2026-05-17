# Deploy Sorteios - Checklist Prático

**Domínio:** `sorteio.overflowmvmt.com`  
**Data de início:** 2026-05-01  
**Status:** Pronto para deploy

---

## 📋 Fase 1: Preparação Local (Seu PC)

### 1.1 Gerar Secrets (execute no terminal)
```bash
# Copiar os comandos abaixo e colar no seu terminal local

# PostgreSQL Password
echo "POSTGRES_PASSWORD: $(openssl rand -base64 24)"

# Session Secret
echo "SESSION_SECRET: $(openssl rand -hex 32)"

# Admin API Key
echo "ADMIN_API_KEY: $(openssl rand -hex 32)"

# SSH Private Key (salvar em arquivo chave.txt)
cat ~/.ssh/id_rsa > /tmp/chave.txt
echo "SSH Private Key salvo em /tmp/chave.txt"
```

**Salvar output em um arquivo seguro (use gerenciador de senha).**

---

## 📋 Fase 2: Configurar GitHub Secrets

### 2.1 Abrir GitHub
1. Ir para: https://github.com/edilsonnewbit/sorteios/settings/secrets/actions
2. Clicar em **"New repository secret"** para cada um:

### 2.2 Adicionar 8 Secrets

```
1. VPS_HOST
   Valor: <IP_DA_VPS> (ex: 195.154.123.45)
   Origem: Hostinger Dashboard → VPS → IP do servidor

2. VPS_USER
   Valor: root
   Origem: Padrão

3. VPS_SSH_PRIVATE_KEY
   Valor: <conteúdo completo da chave privada>
   Origem: cat ~/.ssh/id_rsa (copiar TODO)

4. POSTGRES_USER
   Valor: sorteios_admin
   Origem: Padrão

5. POSTGRES_PASSWORD
   Valor: <senha base64 de 24 chars>
   Origem: openssl rand -base64 24

6. SESSION_SECRET
   Valor: <secret hex de 32 chars>
   Origem: openssl rand -hex 32

7. ADMIN_API_KEY
   Valor: <api key hex de 32 chars>
   Origem: openssl rand -hex 32

8. ADMIN_PASSWORD
   Valor: <senha forte em texto puro>
   Origem: definir manualmente; não usar hash bcrypt
```

**Verificação:** Deve haver **8 secrets** listados em https://github.com/edilsonnewbit/sorteios/settings/secrets/actions

---

## 📋 Fase 3: Preparar VPS (Hostinger)

### 3.1 Conectar via SSH
```bash
ssh root@<IP_DA_VPS>
```

### 3.2 Instalar Docker + Docker Compose
```bash
# Atualizar sistema
apt-get update && apt-get upgrade -y

# Instalar Docker
apt-get install -y docker.io docker-compose curl wget certbot

# Habilitar Docker
systemctl enable docker
systemctl start docker

# Testar
docker --version
docker-compose --version
```

### 3.3 Preparar diretório
```bash
mkdir -p /opt/apps/sorteios/certs
cd /opt/apps/sorteios
```

### 3.4 Clonar repositório
```bash
cd /opt/apps/sorteios
git clone https://github.com/edilsonnewbit/sorteios.git sorteios-prod
cd sorteios-prod
```

### 3.5 Executar setup SSL (Let's Encrypt)
```bash
# IMPORTANTE: Certifique-se que DNS já está apontando para este IP!
bash init-ssl.sh
```

**Output esperado:**
```
✅ Certificate installed successfully!
🎉 SSL setup complete!
```

Se falhar:
- Verificar que DNS está propagado: `nslookup sorteio.overflowmvmt.com`
- Se não resolver, aguardar até 48h
- Ou usar `--test-mode` do certbot primeiro

---

## 📋 Fase 4: Deploy Manual (Primeira Vez)

### 4.1 No VPS
```bash
cd /opt/apps/sorteios/sorteios-prod

# Criar arquivo .env.production
cat > .env.production << EOF
DATABASE_URL=postgresql://sorteios_admin:<POSTGRES_PASSWORD>@db:5432/sorteios
POSTGRES_USER=sorteios_admin
POSTGRES_PASSWORD=<POSTGRES_PASSWORD>
SESSION_SECRET=<SESSION_SECRET>
ADMIN_API_KEY=<ADMIN_API_KEY>
ADMIN_PASSWORD=<ADMIN_PASSWORD>
BACKUP_EMAIL_ENABLED=true
BACKUP_EMAIL_TO=edilsonsilvapro@gmail.com
BACKUP_EMAIL_TIME=02:00
BACKUP_EMAIL_TIMEZONE=America/Recife
LOG_LEVEL=info
ENVIRONMENT=production
DEBUG=False
EOF

# Substituir <POSTGRES_PASSWORD>, <SESSION_SECRET>, <ADMIN_API_KEY>, <ADMIN_PASSWORD> pelos valores reais
```

### 4.2 Iniciar Containers
```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f
```

**Aguardar ~ 40 segundos até ver:**
```
web  | Application startup complete
```

### 4.3 Verificar Health
```bash
# No VPS:
curl -k https://sorteio.overflowmvmt.com/health

# Esperado (HTTP 200):
# {"status":"ok"}
```

Ou no navegador:
- https://sorteio.overflowmvmt.com/health

---

## 📋 Fase 5: Configurar Auto-Deploy (GitHub Actions)

### 5.1 Verificar Workflow
Arquivo já criado: `.github/workflows/deploy-prod.yml`

### 5.2 Testar Deploy
```bash
# Local (seu PC):
cd /Users/edilsonsilva/Clientes/OverFlow/Sorteios
git add .
git commit -m "chore: configure production deployment"
git push origin main
```

### 5.3 Monitorar Deploy
1. Ir para: https://github.com/edilsonnewbit/sorteios/actions
2. Ver workflow **"Deploy Sorteios - Produção (Hostinger)"** rodando
3. Aguardar conclusão (~ 3-5 minutos)

**Status esperado:** ✅ All checks passed

---

## 📋 Fase 6: Validação Final

### 6.1 Acessar Aplicação
```
https://sorteio.overflowmvmt.com
```

Deve carregar admin ou landing page normalmente.

### 6.2 Testar HTTPS
- Link aparece com 🔒 (cadeado verde)
- Nenhum aviso de certificado

### 6.3 Verificar Logs (continuo)
```bash
# No VPS:
ssh root@<IP_VPS>
cd /opt/apps/sorteios/sorteios-prod
docker compose -f docker-compose.prod.yml logs -f web --tail=50
```

---

## 📋 Próximos Deploys (Automáticos)

Após a primeira vez, basta fazer:

```bash
# Seu PC local:
cd /Users/edilsonsilva/Clientes/OverFlow/Sorteios
git commit -m "feat: ....."
git push origin main
```

GitHub Actions vai:
1. Detectar push na branch `main`
2. Build Docker image
3. SSH para VPS
4. Pull código novo
5. Restart containers
6. Health check

**Acompanhar em:** https://github.com/edilsonnewbit/sorteios/actions

---

## 🆘 Troubleshooting

| Problema | Solução |
|----------|---------|
| **502 Bad Gateway** | `docker compose -f docker-compose.prod.yml logs web` |
| **"Connection refused"** | Verificar: `docker compose -f docker-compose.prod.yml ps` |
| **"SSL certificate problem"** | Certificado não disponível em `/opt/apps/sorteios/certs` |
| **Health check timeout** | Aguardar 40s + verificar: `docker compose -f docker-compose.prod.yml logs` |
| **Database connection error** | Verificar POSTGRES_PASSWORD está correto em `.env.production` |
| **SSH falha no GitHub Actions** | VPS_SSH_PRIVATE_KEY incompleto (deve ter BEGIN/END PRIVATE KEY) |

---

## 📞 Suporte

Documentação completa em:
1. **Deploy Guide:** [docs/DEPLOY_HOSTINGER_GUIDE.md](docs/DEPLOY_HOSTINGER_GUIDE.md)
2. **Secrets Setup:** [docs/GITHUB_SECRETS_SETUP.md](docs/GITHUB_SECRETS_SETUP.md)
3. **Nginx Config:** [nginx.conf](nginx.conf)
4. **Docker Compose:** [docker-compose.prod.yml](docker-compose.prod.yml)

---

## ✅ Checklist Final

```
PREPARAÇÃO LOCAL:
[ ] Gerar todos os secrets com openssl
[ ] Salvar secrets em lugar seguro

GITHUB:
[ ] Adicionar 7 secrets em Settings → Secrets
[ ] Verificar que todos aparecem listados
[ ] Verificar que deploy-prod.yml existe em .github/workflows

VPS:
[ ] SSH conecta sem erro
[ ] Docker + Docker Compose instalados
[ ] /opt/apps/sorteios criado
[ ] Repositório clonado
[ ] init-ssl.sh executado com sucesso
[ ] .env.production criado
[ ] docker-compose up -d executado

VALIDAÇÃO:
[ ] https://sorteio.overflowmvmt.com/health responde 200
[ ] HTTPS funciona (cadeado verde)
[ ] GitHub Actions workflow completa sem erro
[ ] Logs mostram "Application startup complete"

PRONTO PARA PRODUÇÃO:
[ ] Todos os itens acima ✅
```

---

**Última atualização:** 2026-05-01 BRT  
**Versão:** 1.0  
**Autor:** GitHub Copilot
