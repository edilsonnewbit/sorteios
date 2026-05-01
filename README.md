# 🎟 Sorteios — Sistema Completo de Rifas Digitais

Sistema completo de sorteios com venda de números, pagamento via PIX, gestão administrativa e design premium.

## Stack

- **Backend:** FastAPI + SQLAlchemy (Python 3.11)
- **Banco:** SQLite (padrão) ou PostgreSQL (produção)
- **Frontend:** Vanilla JS + Jinja2 Templates (sem build step)
- **Deploy:** Docker / docker-compose

---

## Execução Local (Docker)

```bash
# Clonar e iniciar
git clone ...
cp .env.example .env
# Edite .env com suas configurações

docker compose up --build -d
```

Acesse: http://localhost:8000

**Admin:** http://localhost:8000/admin  
(senha: valor de `ADMIN_PASSWORD` no .env)

---

## Configuração do .env

```env
DATABASE_URL=sqlite:////data/sorteios.db
ADMIN_PASSWORD=sua-senha-forte
COOKIE_SECRET=string-aleatoria-de-64-chars

# URL pública do sistema (para links nos e-mails)
BASE_URL=https://seudominio.com

# E-mail SMTP (opcional, mas recomendado)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu@gmail.com
SMTP_PASS=sua-app-password
SMTP_FROM=noreply@seudominio.com
SMTP_FROM_NAME=Sorteios
ADMIN_EMAIL=admin@seudominio.com

# Diretório de backups
BACKUP_DIR=/data/backups
```

---

## Configuração PIX

O PIX é configurado por sorteio no painel admin. Em cada sorteio você define:

| Campo | Descrição | Limite |
|---|---|---|
| **Chave PIX** | CPF, e-mail, telefone ou chave aleatória | — |
| **Nome do recebedor** | Nome que aparece no QR Code | 25 chars |
| **Cidade** | Cidade do recebedor | 15 chars |

O sistema gera automaticamente:
- Payload PIX (Pix Copia e Cola) no padrão EMV BR Code
- QR Code PNG válido para pagamento
- Identificador único por pedido (`ORDxxxxxx`)

---

## Configuração de E-mail

O sistema envia e-mails automáticos para:

1. **Comprador** → após reservar (com QR Code, Pix e link de acompanhamento)
2. **Admin** → a cada nova reserva
3. **Comprador** → quando pagamento for confirmado manualmente
4. **Comprador** → quando reserva expirar/cancelar

Para configurar, preencha as variáveis `SMTP_*` no `.env`.

**Gmail:** Ative "App Password" em https://myaccount.google.com/apppasswords

---

## Fluxo do Comprador

```
/r/{slug}          → Página pública do sorteio
  ↓ Escolhe números + preenche dados
/api/v2/raffles/{slug}/checkout  → Reserva atômica + gera PIX
  ↓ Recebe QR Code + link de acompanhamento
/pedido/{token}    → Acompanhamento do pedido
```

---

## Painel Administrativo

| Rota | Descrição |
|---|---|
| `/admin` | Login |
| `/admin/dashboard` | Dashboard com stats globais |
| `/admin/sorteios` | Listar todos os sorteios |
| `/admin/sorteios/novo` | Criar novo sorteio |
| `/admin/sorteios/{id}` | Editar sorteio + ver pedidos |
| `/admin/pedidos` | Gerenciar pedidos (confirmar/cancelar) |
| `/admin/compradores` | Lista de compradores |
| `/admin/estatisticas` | Estatísticas e ranking |
| `/admin/exportar/csv` | Exportar pedidos em CSV |
| `/admin/backup` | Gerenciar backups do banco |
| `/admin/logs` | Logs de ações admin, e-mails e backups |
| `/admin/configuracoes` | Documentação de configuração |

---

## Backup

### Manual
Acesse `/admin/backup` → **Criar Backup Agora**

### Automático (crontab)
```bash
# Backup diário às 02:00
0 2 * * * curl -X POST http://localhost:8000/admin/backup/criar \
  -H "Cookie: admin_session=SEU_COOKIE" >> /var/log/sorteios-backup.log 2>&1
```

Backups ficam em `./backups/` (ou `BACKUP_DIR` definido no .env).

---

## Segurança

- Rate limiting: checkout (10/min/IP), login (5/5min/IP)
- Row-level locking no banco para evitar duplicidade de números
- Reserva atômica: números reservados em transação única
- Tokens seguros para acompanhamento (via `secrets.token_urlsafe`)
- Cookies HMAC-SHA256 para sessão admin
- Sanitização de uploads de imagem
- Logs de todas as ações administrativas
- Expiração automática de reservas não pagas

---

## Estrutura de Arquivos

```
app/
├── main.py          # Rotas FastAPI (público + admin)
├── models.py        # Modelos SQLAlchemy
├── crud.py          # Operações de banco
├── schemas.py       # Validação Pydantic
├── pix.py           # Gerador PIX BR Code EMV
├── db.py            # Config DB + migração incremental
├── services/
│   ├── email_service.py   # Envio de e-mails SMTP
│   ├── story_service.py   # Geração de Story Instagram
│   ├── backup_service.py  # Backup SQLite/PostgreSQL
│   └── rate_limit.py      # Rate limiting em memória
├── templates/       # Jinja2 HTML templates
└── static/          # CSS, JS, uploads

backups/             # Arquivos de backup do banco
```

---

## Banco de Dados

| Tabela | Descrição |
|---|---|
| `campaigns` | Sorteios/rifas (campos estendidos) |
| `quotas` | Números de cada sorteio |
| `buyers` | Compradores |
| `orders` | Pedidos/reservas |
| `order_items` | Itens de cada pedido (quota ↔ order) |
| `admin_logs` | Logs de ações administrativas |
| `email_logs` | Histórico de e-mails enviados |
| `backup_logs` | Histórico de backups |

---

## Deploy com PostgreSQL

```yaml
# No docker-compose.yml, altere o serviço web:
environment:
  DATABASE_URL: "postgresql://postgres:postgres@db:5432/sorteios"
```

---

## Arte para Instagram Story

Acesse: `GET /r/{slug}/story.png`

Gera uma imagem 1080×1920 com:
- Imagem do prêmio (se configurada)
- Título do sorteio
- Barra de progresso de vendas
- Preço por número
- QR Code (opcional)
- CTA de participação

---

## Compartilhamento

Cada sorteio inclui botões prontos para:
- WhatsApp, Telegram, X/Twitter
- Copiar link
- Copiar mensagem pronta para divulgação
- Download do Story para Instagram

---

## Contribuição / Próximos Passos

- [ ] Integração com webhook de pagamento (Mercado Pago / PagSeguro)
- [ ] Dashboard em tempo real com WebSockets
- [ ] Autenticação multi-admin com permissões
- [ ] Paginação no grid de números (para sorteios >5000 números)
- [ ] API pública documentada com Swagger (/docs)
