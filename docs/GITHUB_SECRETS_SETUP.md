# GitHub Secrets & Variables - Checklist

**Repositório:** `edilsonnewbit/sorteios`  
**Domínio:** `sorteio.overflowmvmt.com`  
**Abordagem:** GHCR Registry + Hostinger Deploy Action

---

## 1. Gerar Valores Seguros (Local)

Abra o terminal local e execute os comandos abaixo para gerar os valores necessários:

```bash
# 1. PostgreSQL Password (24 caracteres aleatórios)
openssl rand -base64 24
# ↓ Exemplo de output:
# xQ8nK2pL9kV5mN3zZ7bY6xW4jK1fD9sE

# 2. Session Secret (32 caracteres hexadecimais)
openssl rand -hex 32
# ↓ Exemplo de output:
# a7f2c8e1b9d4k3n5m7z2x6v4w1q9s8r3

# 3. Admin API Key (32 caracteres hexadecimais)
openssl rand -hex 32
# ↓ Exemplo de output:
# 5m2k8n3v7z1x9w4q6j1f5d0s2l3a8p4c
```

**Salve os valores em um arquivo local seguro (ou use um gerenciador de senhas).**

---

## 2. Acessar GitHub Secrets

### 2.1 No navegador
1. Ir para: https://github.com/edilsonnewbit/sorteios/settings/secrets/actions
2. Ou navegar manualmente:
   - GitHub → Seu repositório **sorteios**
   - Settings → Secrets and variables → Actions

---

## 3. Adicionar Repository Secrets

Clicar em **"New repository secret"** para cada um abaixo:

### 3.1 Hostinger Connection (Obrigatório)
| Name | Value | Gerado com | Exemplo |
|------|-------|-----------|---------|
| `HOSTINGER_API_KEY` | API Key da Hostinger | Hostinger Dashboard → Account → API | `a1b2c3d4e5f6g7h8...` |
| `POSTGRES_USER` | Nome do usuário | Manual (ou usar padrão) | `sorteios_admin` |
| `POSTGRES_PASSWORD` | Senha forte (24+ chars base64) | `openssl rand -base64 24` | `xQ8nK2pL9kV5mN3zZ7bY6xW4jK1fD9sE` |
| `SESSION_SECRET` | Secret para cookies/sessão (32 hex) | `openssl rand -hex 32` | `a7f2c8e1b9d4k3n5m7z2x6v4w1q9s8r3` |
| `ADMIN_API_KEY` | Admin API key (32 hex) | `openssl rand -hex 32` | `5m2k8n3v7z1x9w4q6j1f5d0s2l3a8p4c` |
| `ADMIN_PASSWORD` | Senha do login `/admin/login` | Manual, texto puro | `senha-forte-aqui` |

**✅ Instruções:**
1. HOSTINGER_API_KEY: Gerar em Hostinger Dashboard
   - Acesso: Account → API → Generate API Key
   - Permissões: VPS Deploy
2. POSTGRES_USER: Padrão `sorteios_admin` ou customizar
3. POSTGRES_PASSWORD: `openssl rand -base64 24`
4. SESSION_SECRET: `openssl rand -hex 32`
5. ADMIN_API_KEY: `openssl rand -hex 32`
6. ADMIN_PASSWORD: senha forte em texto puro, sem hash

---

## 4. Adicionar Repository Variables

### 4.1 No navegador
1. Ir para: https://github.com/edilsonnewbit/sorteios/settings/variables/actions
2. Clicar em **"New repository variable"** para cada um:

| Name | Value | 
|------|-------|
| `HOSTINGER_VM_ID` | ID da VPS na Hostinger |

**✅ Instruções:**
- HOSTINGER_VM_ID: 
  - Hostinger Dashboard → VPS → clicar VPS
  - URL será: `/hosting/vps/manage/12345`
  - Copiar `12345` (o número)

---

## 5. Checklist de Preenchimento

Copie e cole no seu editor local para marcar:

```
SECRETS (obrigatório):
[ ] HOSTINGER_API_KEY: [copiar de Hostinger]
[ ] POSTGRES_USER: sorteios_admin
[ ] POSTGRES_PASSWORD: [senha base64 de 24 chars]
[ ] SESSION_SECRET: [secret hex de 32 chars]
[ ] ADMIN_API_KEY: [api key hex de 32 chars]
[ ] ADMIN_PASSWORD: [senha forte em texto puro]

VARIABLES (obrigatório):
[ ] HOSTINGER_VM_ID: [ID da VPS]
```

---

## 6. Verificação (GitHub)

Após adicionar todos:

1. Ir para https://github.com/edilsonnewbit/sorteios/settings/secrets/actions
   - Deve aparecer **6 secrets**

2. Ir para https://github.com/edilsonnewbit/sorteios/settings/variables/actions
   - Deve aparecer **1 variable**

3. Cada um vai mostrar "now" ou similar na coluna "Last updated"

---

## 7. Obter HOSTINGER_API_KEY

### 7.1 Hostinger Dashboard
1. Acessar: https://hpanel.hostinger.com
2. Menu superior direito → Account
3. Esquerda → API
4. Clicar "Generate API Key"
5. Nome: `sorteios-deploy` ou similar
6. Permissões: Marcar `VPS` e `Containers`
7. Gerar e copiar chave
8. **⚠️ Guardar com segurança!** (só aparece 1x)

---

## 8. Obter HOSTINGER_VM_ID

### 8.1 Hostinger Dashboard
1. Acessar: https://hpanel.hostinger.com
2. Esquerda → Hosting → VPS
3. Clicar em sua VPS
4. URL resultará em: `https://hpanel.hostinger.com/hosting/vps/manage/123456`
5. Número `123456` = VM_ID
6. Copiar para GitHub `HOSTINGER_VM_ID`

---

## 9. Fluxo de Deploy com Secrets

Quando fizer push na branch `main`:

```
1. GitHub Actions detecta push
2. Faz login no GHCR (Container Registry)
3. Build Docker image: ghcr.io/edilsonnewbit/sorteios:SHA
4. Push image para GHCR
5. Validação de variáveis (check-hostinger-env.sh)
6. Hostinger Deploy Action:
   - usa HOSTINGER_API_KEY + HOSTINGER_VM_ID
   - puxa image do GHCR
   - injeta variáveis de ambiente
   - restart containers
7. Verifica health em https://sorteio.overflowmvmt.com/health
```

---

## 10. Troubleshooting

| Erro | Solução |
|------|---------|
| `401 Unauthorized` na ação Hostinger | HOSTINGER_API_KEY inválida ou expirada |
| `Virtual machine not found` | HOSTINGER_VM_ID incorreta |
| `Connection refused` | VPS não está rodando ou firewall bloqueando |
| `Validation failed` | Check script encontrou variável inválida (ver logs) |
| ` Secret not found` | Secret não foi adicionado ou nome errado |

---

## 11. Rotação de Secrets (Segurança)

A cada 6 meses, gerar novos valores:

```bash
# Gerar novo POSTGRES_PASSWORD
openssl rand -base64 24

# Gerar novo SESSION_SECRET
openssl rand -hex 32

# Gerar novo ADMIN_API_KEY
openssl rand -hex 32
```

Atualizar em GitHub `Settings > Secrets and variables > Actions`

---

## 12. Próximos Passos

1. ✅ Adicionar todos os 5 Secrets
2. ✅ Adicionar a 1 Variable
3. ✅ Fazer push de `main` para gatilhar o workflow
4. ✅ Monitorar GitHub Actions (Actions tab)
5. ✅ Verificar deploy em https://sorteio.overflowmvmt.com/health

---

**Última atualização:** 2026-05-01 BRT  
**Versão:** 2.0 (Hostinger Deploy Action)  
**Autor:** GitHub Copilot
