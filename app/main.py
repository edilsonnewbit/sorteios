from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager, suppress
from sqlalchemy.orm import Session
from . import db, crud, schemas
from . import auth as auth_mod
from .pix import generate_pix_payload
from .services import rate_limit as rl
from .services import email_service as mail
from .services import story_service
from .services import backup_service
from io import BytesIO
import asyncio
import datetime
import os
import hashlib
import hmac
import logging
import shutil
import uuid
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or "admin123"
_COOKIE_SECRET = os.getenv("COOKIE_SECRET", "change-me-in-production")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
UPLOAD_DIR = "/data/uploads"
BACKUP_EMAIL_TO = os.getenv("BACKUP_EMAIL_TO", "edilsonsilvapro@gmail.com")
BACKUP_EMAIL_TIME = os.getenv("BACKUP_EMAIL_TIME", "02:00")
BACKUP_EMAIL_TIMEZONE = os.getenv("BACKUP_EMAIL_TIMEZONE", "America/Recife")
BACKUP_EMAIL_ENABLED = os.getenv("BACKUP_EMAIL_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("backups", exist_ok=True)


# ─── Cookie Auth ──────────────────────────────────────────────────────────────

def _sign_cookie(value: str) -> str:
    sig = hmac.new(_COOKIE_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{value}.{sig}"


def _verify_cookie(raw: str) -> bool:
    if not raw or "." not in raw:
        return False
    value, sig = raw.rsplit(".", 1)
    expected = hmac.new(_COOKIE_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(sig, expected)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─── Lifespan ─────────────────────────────────────────────────────────────────

def _backup_email_next_run_seconds() -> float:
    try:
        hour_s, minute_s = (BACKUP_EMAIL_TIME.split(":", 1) + ["0"])[:2]
        hour = max(0, min(23, int(hour_s)))
        minute = max(0, min(59, int(minute_s)))
    except ValueError:
        logger.warning("BACKUP_EMAIL_TIME inválido (%s), usando 02:00", BACKUP_EMAIL_TIME)
        hour, minute = 2, 0
    try:
        tz = ZoneInfo(BACKUP_EMAIL_TIMEZONE)
    except Exception:
        logger.warning("BACKUP_EMAIL_TIMEZONE inválido (%s), usando UTC", BACKUP_EMAIL_TIMEZONE)
        tz = ZoneInfo("UTC")
    now = datetime.datetime.now(tz)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += datetime.timedelta(days=1)
    return (next_run - now).total_seconds()


def _run_daily_backup_email() -> None:
    session = db.SessionLocal()
    try:
        result = backup_service.create_backup()
        filename = result.get("filename") or "failed"
        status = "success" if not result.get("error") else "failed"
        crud.log_backup(session, filename, result.get("size_bytes"), status, result.get("error"))

        if result.get("error"):
            subject = "Falha no backup diário - Sorteios"
            html = (
                "<h2>Falha no backup diário</h2>"
                f"<p>Erro: <code>{result.get('error')}</code></p>"
            )
            ok, err = mail.send_email(BACKUP_EMAIL_TO, subject, html)
            crud.log_email(session, BACKUP_EMAIL_TO, subject, "sent" if ok else "failed", error=err)
            return

        fpath = backup_service.get_backup_path(filename)
        if not fpath:
            raise RuntimeError(f"Backup criado, mas arquivo não encontrado: {filename}")

        size_mb = (result.get("size_bytes") or 0) / (1024 * 1024)
        subject = f"Backup diário Sorteios - {filename}"
        html = (
            "<h2>Backup diário concluído</h2>"
            f"<p>Arquivo: <strong>{filename}</strong></p>"
            f"<p>Tamanho: {size_mb:.2f} MB</p>"
            "<p>O backup está anexado a este e-mail.</p>"
        )
        ok, err = mail.send_email(
            BACKUP_EMAIL_TO,
            subject,
            html,
            attachments=[(fpath, filename)],
        )
        crud.log_email(session, BACKUP_EMAIL_TO, subject, "sent" if ok else "failed", error=err)
        crud.log_admin_action(session, "backup_email", f"Arquivo: {filename} enviado para {BACKUP_EMAIL_TO}", "system")
    except Exception as e:
        logger.exception("Falha no job de backup diário por e-mail")
        crud.log_backup(session, "failed", None, "failed", str(e))
    finally:
        session.close()


async def _daily_backup_email_loop() -> None:
    while True:
        wait_seconds = _backup_email_next_run_seconds()
        logger.info(
            "Backup diário por e-mail agendado para %s (%s), destinatário=%s",
            BACKUP_EMAIL_TIME,
            BACKUP_EMAIL_TIMEZONE,
            BACKUP_EMAIL_TO,
        )
        await asyncio.sleep(wait_seconds)
        await asyncio.to_thread(_run_daily_backup_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("Database initialized")
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD") or "admin123"
    if admin_email:
        db.seed_admin(admin_email, admin_password)
    else:
        db.seed_admin("admin@sorteios.local", admin_password)
    backup_task = None
    if BACKUP_EMAIL_ENABLED and BACKUP_EMAIL_TO:
        backup_task = asyncio.create_task(_daily_backup_email_loop())
    try:
        yield
    finally:
        if backup_task:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task


app = FastAPI(title="Sorteios", version="2.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static/uploads", StaticFiles(directory="/data/uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Register custom Jinja2 filters
import json as _json
from markupsafe import Markup as _Markup
templates.env.filters["tojson"] = lambda v, **kw: _Markup(_json.dumps(v, ensure_ascii=False))
templates.env.globals["enumerate"] = enumerate

_STATUS_PT = {
    # pedidos
    "paid": "Pago", "pending": "Pendente", "cancelled": "Cancelado", "expired": "Expirado",
    # sorteios
    "active": "Ativo", "drawn": "Sorteado", "closed": "Encerrado", "sold_out": "Esgotado",
    # usuários
    "approved": "Aprovado", "rejected": "Rejeitado",
    # cotas
    "available": "Disponível", "reserved": "Reservado", "blocked": "Bloqueado",
}
templates.env.filters["status_pt"] = lambda v: _STATUS_PT.get(v, v)


# ─── Dependencies ─────────────────────────────────────────────────────────────

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _admin_user(request: Request):
    """Returns user dict if admin session valid, else None."""
    user = auth_mod.get_current_user(request)
    if user and user.get("role") == "admin":
        return user
    # Legacy fallback: old cookie-based admin session
    if _verify_cookie(request.cookies.get("admin_session", "")):
        return {"id": 0, "role": "admin", "name": "Admin"}
    return None


def require_admin(request: Request):
    if not _admin_user(request):
        raise HTTPException(status_code=403, detail="Acesso negado")


def optional_admin(request: Request) -> bool:
    return _admin_user(request) is not None


def _is_super_admin(db_user) -> bool:
    if not db_user or db_user.role != "admin":
        return False
    super_admin_email = os.getenv("ADMIN_EMAIL", "admin@sorteios.local").strip().lower()
    return (db_user.email or "").strip().lower() == super_admin_email


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ─── Homepage ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_db)):
    user = auth_mod.get_current_user(request)
    # Redirect logged-in users to their area
    if user:
        if user.get("role") == "admin":
            return RedirectResponse("/admin/dashboard", status_code=302)
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "landing.html", {"base_url": BASE_URL})


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Campaigns (legacy)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/campaigns", response_model=schemas.CampaignSummary)
def api_create_campaign(item: schemas.CampaignCreate, session: Session = Depends(get_db)):
    if item.goal_amount <= 0 or item.price_per_quota <= 0:
        raise HTTPException(status_code=422, detail="Valores devem ser positivos")
    if item.price_per_quota > item.goal_amount:
        raise HTTPException(status_code=422, detail="Valor por cota não pode exceder a meta")
    c = crud.create_campaign(
        session,
        item.title,
        item.goal_amount,
        item.price_per_quota,
        item.pix_key,
        item.draw_date,
        (item.share_message_template.strip() if item.share_message_template else None),
    )
    logger.info("Campaign created: id=%s slug=%s", c.id, c.slug)
    return c


@app.get("/api/campaigns", response_model=list[schemas.CampaignSummary])
def api_list_campaigns(session: Session = Depends(get_db)):
    return crud.list_campaigns(session)


@app.get("/api/campaigns/{campaign_id}/quotas")
def api_list_quotas(campaign_id: int, session: Session = Depends(get_db)):
    return crud.list_quotas(session, campaign_id)


@app.post("/api/campaigns/{campaign_id}/reserve")
def api_reserve(campaign_id: int, number: int = Form(...), buyer: str = Form(...), session: Session = Depends(get_db)):
    buyer = buyer.strip()
    if not buyer:
        raise HTTPException(status_code=422, detail="Nome do comprador é obrigatório")
    q = crud.reserve_quota(session, campaign_id, number, buyer)
    if not q:
        raise HTTPException(status_code=409, detail="Cota indisponível")
    return {"ok": True, "quota_id": q.id}


@app.post("/api/checkout")
def api_checkout(campaign_id: int = Form(...), quota_ids: str = Form(...), session: Session = Depends(get_db)):
    ids = [int(x) for x in quota_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="Nenhuma cota informada")
    campaign = crud.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    if not campaign.pix_key:
        raise HTTPException(status_code=400, detail="Campanha sem chave PIX configurada")
    amount = len(ids) * campaign.price_per_quota
    txid = f"SORT{ids[0]}"
    payload = generate_pix_payload(
        campaign.pix_key, amount,
        description=f"Sorteio {campaign.title}"[:99],
        txid=txid,
    )
    import qrcode
    img = qrcode.make(payload)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="image/png",
        headers={"X-Pix-Payload": payload, "X-Amount": f"{amount:.2f}"},
    )


@app.post("/api/confirm")
def api_confirm_quota(quota_ids: str = Form(...), session: Session = Depends(get_db), _: None = Depends(require_admin)):
    ids = [int(x) for x in quota_ids.split(",") if x.strip()]
    qs = crud.mark_paid(session, ids)
    logger.info("Marked paid: %s", ids)
    return {"ok": True, "paid": [q.id for q in qs]}


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC PAGES — Sorteios
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/s/{slug}", response_class=HTMLResponse)
def view_campaign_legacy(request: Request, slug: str, session: Session = Depends(get_db)):
    """Mantém compatibilidade com links antigos — redireciona para a nova página."""
    c = crud.get_campaign_by_slug(session, slug)
    if not c:
        raise HTTPException(status_code=404, detail="Sorteio não encontrado")
    return RedirectResponse(f"/r/{slug}", status_code=301)


@app.get("/r/{slug}", response_class=HTMLResponse)
def view_raffle_public(request: Request, slug: str, session: Session = Depends(get_db),
                       ref: str | None = None):
    c = crud.get_campaign_by_slug(session, slug)
    if not c:
        raise HTTPException(status_code=404, detail="Sorteio não encontrado")
    stats = crud.get_raffle_stats(session, c.id)
    share_link = f"{BASE_URL}/r/{slug}"
    default_share_message = (
        f"{c.title} — Participe do sorteio! "
        f"Números a partir de R$ {c.price_per_quota:.2f}. "
        f"Acesse: {share_link}"
    )
    share_message = default_share_message
    if c.share_message_template:
        share_message = c.share_message_template
        share_message = share_message.replace("{titulo}", c.title)
        share_message = share_message.replace("{preco}", f"{c.price_per_quota:.2f}")
        share_message = share_message.replace("{link}", share_link)

    return templates.TemplateResponse(request, "raffle_public.html", {
        "campaign": c,
        "stats": stats,
        "base_url": BASE_URL,
        "ref": ref or "",
        "share_message": share_message,
    })


@app.get("/pedido/{token}", response_class=HTMLResponse)
def view_order_tracking(request: Request, token: str, session: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not rl.order_query_allowed(ip):
        raise HTTPException(status_code=429, detail="Muitas consultas. Tente novamente em alguns segundos.")
    order = crud.get_order_by_token(session, token)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    numbers = [item.quota.number for item in order.items if item.quota]
    return templates.TemplateResponse(request, "order_tracking.html", {
        "order": order,
        "numbers": sorted(numbers),
        "base_url": BASE_URL,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API v2 — Checkout & Orders
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v2/raffles/{slug}")
def api_raffle_detail(slug: str, session: Session = Depends(get_db)):
    c = crud.get_campaign_by_slug(session, slug)
    if not c:
        raise HTTPException(status_code=404, detail="Sorteio não encontrado")
    stats = crud.get_raffle_stats(session, c.id)
    quotas = crud.list_quotas(session, c.id)
    return {
        "id": c.id,
        "title": c.title,
        "slug": c.slug,
        "description": c.description,
        "prize_image_url": c.prize_image_url,
        "prize_value": c.prize_value,
        "rules": c.rules,
        "price_per_quota": c.price_per_quota,
        "draw_date": c.draw_date.isoformat() if c.draw_date else None,
        "status": c.status,
        "max_per_person": c.max_per_person or 10,
        "reservation_expires_minutes": c.reservation_expires_minutes or 30,
        "winner_quota_id": c.winner_quota_id,
        "stats": stats,
        "quotas": [
            {"id": q.id, "number": q.number, "status": q.status, "paid": q.paid}
            for q in quotas
        ],
    }


@app.post("/api/v2/raffles/{slug}/checkout")
async def api_v2_checkout(request: Request, slug: str, session: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not rl.checkout_allowed(ip):
        raise HTTPException(status_code=429, detail="Muitos pedidos seguidos. Aguarde um momento.")

    body = await request.json()
    campaign = crud.get_campaign_by_slug(session, slug)
    if not campaign:
        raise HTTPException(status_code=404, detail="Sorteio não encontrado")

    numbers = body.get("numbers", [])
    buyer_data = body.get("buyer", {})

    if not numbers:
        raise HTTPException(status_code=422, detail="Selecione ao menos um número")

    buyer_name = (buyer_data.get("name") or "").strip()
    buyer_whatsapp = (buyer_data.get("whatsapp") or "").strip()
    buyer_email = (buyer_data.get("email") or "").strip() or None
    buyer_cpf = (buyer_data.get("cpf") or "").strip() or None

    if not buyer_name:
        raise HTTPException(status_code=422, detail="Nome é obrigatório")
    if not buyer_whatsapp or len(buyer_whatsapp) < 10:
        raise HTTPException(status_code=422, detail="WhatsApp inválido")

    result = crud.checkout_atomic(
        db=session,
        campaign_id=campaign.id,
        numbers=numbers,
        buyer_name=buyer_name,
        buyer_whatsapp=buyer_whatsapp,
        buyer_email=buyer_email,
        buyer_cpf=buyer_cpf,
    )

    if result["error"]:
        raise HTTPException(status_code=409, detail=result["error"])

    order = result["order"]

    # Send emails asynchronously (best-effort)
    _send_order_emails(session, order, campaign, numbers, buyer_name, buyer_email, buyer_whatsapp)

    # Log the action
    crud.log_admin_action(
        session, "new_order",
        f"Pedido #{order.id} - {buyer_name} - {len(numbers)} números - R${order.total_amount:.2f}",
        ip,
    )

    return {
        "ok": True,
        "token": order.token,
        "order_id": order.id,
        "total": order.total_amount,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "pix_payload": order.pix_payload,
        "qr_code_base64": order.qr_code_base64,
        "numbers": sorted(numbers),
        "tracking_url": f"{BASE_URL}/pedido/{order.token}",
    }


def _send_order_emails(session, order, campaign, numbers, buyer_name, buyer_email, buyer_whatsapp):
    """Envia e-mails de confirmação (best-effort)."""
    tracking_url = f"{BASE_URL}/pedido/{order.token}"
    expires_str = order.expires_at.strftime("%d/%m/%Y %H:%M") if order.expires_at else "—"

    if buyer_email:
        html = mail.build_order_confirmation_email(
            order_token=order.token,
            raffle_title=campaign.title,
            buyer_name=buyer_name,
            numbers=numbers,
            total_amount=order.total_amount,
            pix_payload=order.pix_payload,
            expires_at=expires_str,
            tracking_url=tracking_url,
            has_qr=bool(order.qr_code_base64),
        )
        ok, err = mail.send_email(
            buyer_email,
            f"Confirmação de reserva — {campaign.title}",
            html,
            order.qr_code_base64,
        )
        crud.log_email(session, buyer_email, f"Confirmação - {campaign.title}",
                       "sent" if ok else "failed", order.id, err)

    # Admin notification
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if admin_email:
        admin_html = mail.build_admin_new_order_email(
            raffle_title=campaign.title,
            buyer_name=buyer_name,
            buyer_whatsapp=buyer_whatsapp,
            numbers=numbers,
            total_amount=order.total_amount,
            order_token=order.token,
            admin_url=f"{BASE_URL}/admin/pedidos",
        )
        mail.send_email(admin_email, f"Nova reserva — {campaign.title}", admin_html)


@app.get("/api/v2/orders/{token}")
def api_order_status(token: str, request: Request, session: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not rl.order_query_allowed(ip):
        raise HTTPException(status_code=429, detail="Muitas consultas.")
    order = crud.get_order_by_token(session, token)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    numbers = sorted(item.quota.number for item in order.items if item.quota)
    return {
        "id": order.id,
        "token": order.token,
        "status": order.status,
        "total_amount": order.total_amount,
        "pix_payload": order.pix_payload,
        "qr_code_base64": order.qr_code_base64,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "numbers": numbers,
        "buyer": {
            "name": order.buyer.name if order.buyer else "",
            "whatsapp": order.buyer.whatsapp if order.buyer else "",
        } if order.buyer else None,
        "campaign": {
            "title": order.campaign.title,
            "slug": order.campaign.slug,
            "prize_image_url": order.campaign.prize_image_url,
        } if order.campaign else None,
    }


@app.get("/r/{slug}/story.png")
def raffle_story_image(slug: str, session: Session = Depends(get_db)):
    campaign = crud.get_campaign_by_slug(session, slug)
    if not campaign:
        raise HTTPException(status_code=404)
    stats = crud.get_raffle_stats(session, campaign.id)
    img_bytes = story_service.generate_story(
        raffle_title=campaign.title,
        prize_description=campaign.description or "",
        price_per_quota=campaign.price_per_quota,
        total=stats.get("total", 0),
        sold=stats.get("reserved", 0) + stats.get("paid", 0),
        share_url=f"{BASE_URL}/r/{slug}",
        prize_image_url=campaign.prize_image_url,
    )
    if not img_bytes:
        raise HTTPException(status_code=500, detail="Story generation not available")
    return StreamingResponse(BytesIO(img_bytes), media_type="image/png",
                             headers={"Content-Disposition": f'attachment; filename="story_{slug}.png"'})


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC — Auth (Login / Register / Logout)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = auth_mod.get_current_user(request)
    if user:
        dest = "/admin/dashboard" if user.get("role") == "admin" else "/dashboard"
        return RedirectResponse(dest, status_code=302)
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(request, "login.html", {"next": next_url})


@app.post("/login")
def do_login(request: Request, email: str = Form(...), password: str = Form(...),
             next: str = Form(""), session: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not rl.login_allowed(ip):
        return templates.TemplateResponse(request, "login.html",
            {"error": "Muitas tentativas. Aguarde alguns minutos.", "next": next}, status_code=429)

    user = crud.get_user_by_email(session, email)
    if not user or not auth_mod.verify_password(password, user.password_hash):
        logger.warning("Failed login: email=%s ip=%s", email, ip)
        crud.log_admin_action(session, "login_failed", f"email={email} ip={ip}", ip)
        return templates.TemplateResponse(request, "login.html",
            {"error": "E-mail ou senha incorretos.", "next": next}, status_code=401)

    if user.status == "pending":
        return templates.TemplateResponse(request, "login.html",
            {"error": "Sua conta ainda não foi aprovada pelo administrador.", "next": next}, status_code=403)
    if user.status == "rejected":
        return templates.TemplateResponse(request, "login.html",
            {"error": "Seu cadastro foi recusado. Entre em contato com o suporte.", "next": next}, status_code=403)

    dest = next if next and next.startswith("/") else ("/admin/dashboard" if user.role == "admin" else "/dashboard")
    resp = RedirectResponse(dest, status_code=303)
    auth_mod.set_session_cookie(resp, user.id, user.role, user.name)
    crud.log_admin_action(session, "login_success", f"user_id={user.id} email={user.email}", ip)
    return resp


@app.get("/logout")
def do_logout():
    resp = RedirectResponse("/login", status_code=303)
    auth_mod.clear_session_cookie(resp)
    resp.delete_cookie("admin_session")  # legacy
    return resp


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    user = auth_mod.get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "register.html", {})


@app.post("/register")
def do_register(request: Request, session: Session = Depends(get_db),
                name: str = Form(...), email: str = Form(...),
                company_name: str = Form(""), phone: str = Form(""),
                password: str = Form(...), password2: str = Form(...)):
    error = None
    if len(password) < 8:
        error = "A senha deve ter pelo menos 8 caracteres."
    elif password != password2:
        error = "As senhas não conferem."
    elif crud.get_user_by_email(session, email):
        error = "Este e-mail já está cadastrado."
    if error:
        return templates.TemplateResponse(request, "register.html", {
            "error": error, "form": {"name": name, "email": email,
                                     "company_name": company_name, "phone": phone}})
    pwd_hash = auth_mod.hash_password(password)
    crud.create_user(session, email, name, company_name or None, phone or None, pwd_hash)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "register", f"novo cadastro: {email}", ip)
    return templates.TemplateResponse(request, "register.html", {"success": True})


# ══════════════════════════════════════════════════════════════════════════════
#  ORGANIZER — Dashboard
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_home(request: Request, session: Session = Depends(get_db)):
    user = auth_mod.get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/dashboard", status_code=303)
    if user.get("role") == "admin":
        return RedirectResponse("/admin/dashboard", status_code=302)
    db_user = crud.get_user(session, user["id"])
    if not db_user or db_user.status != "approved":
        resp = RedirectResponse("/login", status_code=303)
        auth_mod.clear_session_cookie(resp)
        return resp
    campaigns = crud.list_campaigns_by_owner(session, db_user.id)
    stats_map = {c.id: crud.get_raffle_stats(session, c.id) for c in campaigns}
    global_s = {"total": len(campaigns),
                "active": sum(1 for c in campaigns if c.status == "active")}
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": db_user,
        "campaigns": campaigns,
        "stats_map": stats_map,
        "global_stats": global_s,
        "base_url": BASE_URL,
    })


@app.get("/dashboard/sorteios/novo", response_class=HTMLResponse)
def dash_raffle_new(request: Request):
    user = auth_mod.get_current_user(request)
    if not user or user.get("role") == "admin":
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard_raffle_form.html",
                                      {"campaign": None, "user": user, "mode": "create"})


@app.post("/dashboard/sorteios/novo")
async def dash_raffle_create(
    request: Request, session: Session = Depends(get_db),
    title: str = Form(...), description: str = Form(""),
    share_message_template: str = Form(""),
    prize_value: str = Form(""), rules: str = Form(""),
    goal_amount: float = Form(...), price_per_quota: float = Form(...),
    max_per_person: int = Form(10), pix_key: str = Form(""),
    pix_receiver_name: str = Form("SORTEIOS"), pix_receiver_city: str = Form("SAO PAULO"),
    draw_date: str = Form(""), reservation_expires_minutes: int = Form(30),
    prize_image: UploadFile | None = File(None),
):
    user = auth_mod.get_current_user(request)
    if not user or user.get("role") == "admin":
        return RedirectResponse("/login", status_code=303)
    db_user = crud.get_user(session, user["id"])
    if not db_user or db_user.status != "approved":
        return RedirectResponse("/login", status_code=303)

    used = crud.count_user_raffles(session, db_user.id)
    if used >= db_user.max_raffles:
        return templates.TemplateResponse(request, "dashboard_raffle_form.html", {
            "campaign": None, "user": user, "mode": "create",
            "error": f"Você atingiu o limite de {db_user.max_raffles} sorteios."})

    prize_image_url = None
    if prize_image and prize_image.filename:
        ext = os.path.splitext(prize_image.filename)[-1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            fname = f"{uuid.uuid4().hex}{ext}"
            with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
                shutil.copyfileobj(prize_image.file, f)
            prize_image_url = f"/static/uploads/{fname}"

    data = {
        "title": title.strip(), "description": description.strip() or None,
        "share_message_template": share_message_template.strip() or None,
        "prize_image_url": prize_image_url,
        "prize_value": float(prize_value) if prize_value.strip() else None,
        "rules": rules.strip() or None, "goal_amount": goal_amount,
        "price_per_quota": price_per_quota, "max_per_person": max_per_person,
        "pix_key": pix_key.strip() or None,
        "pix_receiver_name": pix_receiver_name.strip() or "SORTEIOS",
        "pix_receiver_city": pix_receiver_city.strip() or "SAO PAULO",
        "draw_date": draw_date.strip() or None,
        "reservation_expires_minutes": reservation_expires_minutes,
        "owner_id": db_user.id,
    }
    crud.create_raffle(session, data)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/dashboard/sorteios/{campaign_id}", response_class=HTMLResponse)
def dash_raffle_detail(request: Request, campaign_id: int, session: Session = Depends(get_db)):
    user = auth_mod.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    campaign = crud.get_campaign(session, campaign_id)
    if not campaign or (user.get("role") != "admin" and campaign.owner_id != user.get("id")):
        raise HTTPException(status_code=404)
    stats = crud.get_raffle_stats(session, campaign.id)
    orders = crud.list_orders_by_campaign(session, campaign_id, limit=50)
    return templates.TemplateResponse(request, "dashboard_raffle_detail.html", {
        "campaign": campaign, "stats": stats, "orders": orders,
        "user": user, "base_url": BASE_URL,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Auth
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if _verify_cookie(request.cookies.get("admin_session", "")):
        return RedirectResponse("/admin/dashboard")
    return templates.TemplateResponse(request, "admin_login.html")


@app.post("/admin/login")
def admin_do_login(request: Request, password: str = Form(...), session: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not rl.login_allowed(ip):
        return templates.TemplateResponse(request, "admin_login.html",
                                          {"error": "Muitas tentativas. Aguarde alguns minutos."})
    if password != ADMIN_PASSWORD:
        logger.warning("Failed admin login from %s", ip)
        crud.log_admin_action(session, "login_failed", f"IP: {ip}", ip)
        return templates.TemplateResponse(request, "admin_login.html", {"error": "Senha inválida"})
    crud.log_admin_action(session, "login_success", f"IP: {ip}", ip)
    resp = RedirectResponse("/admin/dashboard", status_code=303)
    signed = _sign_cookie("admin")
    resp.set_cookie("admin_session", signed, httponly=True, samesite="lax", max_age=28800)
    return resp


@app.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin", status_code=303)
    resp.delete_cookie("admin_session")
    resp.delete_cookie("session")
    return resp


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Dashboard & Pages
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, session: Session = Depends(get_db), _: None = Depends(require_admin)):
    campaigns = crud.list_campaigns(session)
    global_stats = crud.get_global_stats(session)
    recent_orders = crud.list_orders(session, limit=10)
    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "campaigns": campaigns,
        "global_stats": global_stats,
        "recent_orders": recent_orders,
    })


@app.get("/admin/sorteios", response_class=HTMLResponse)
def admin_raffles_list(request: Request, session: Session = Depends(get_db), _: None = Depends(require_admin)):
    campaigns = crud.list_campaigns(session)
    stats_map = {c.id: crud.get_raffle_stats(session, c.id) for c in campaigns}
    return templates.TemplateResponse(request, "admin_raffles.html", {
        "campaigns": campaigns,
        "stats_map": stats_map,
    })


@app.get("/admin/sorteios/novo", response_class=HTMLResponse)
def admin_raffle_new(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(request, "admin_raffle_form.html", {"campaign": None})


@app.post("/admin/sorteios/novo")
async def admin_raffle_create(
    request: Request,
    session: Session = Depends(get_db),
    _: None = Depends(require_admin),
    title: str = Form(...),
    description: str = Form(""),
    share_message_template: str = Form(""),
    prize_value: str = Form(""),
    rules: str = Form(""),
    goal_amount: float = Form(...),
    price_per_quota: float = Form(...),
    max_per_person: int = Form(10),
    pix_key: str = Form(""),
    pix_receiver_name: str = Form("SORTEIOS"),
    pix_receiver_city: str = Form("SAO PAULO"),
    draw_date: str = Form(""),
    reservation_expires_minutes: int = Form(30),
    prize_image: UploadFile | None = File(None),
):
    prize_image_url = None
    if prize_image and prize_image.filename:
        ext = os.path.splitext(prize_image.filename)[-1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return templates.TemplateResponse(request, "admin_raffle_form.html",
                                              {"error": "Imagem inválida. Use JPG, PNG ou WEBP.", "campaign": None})
        fname = f"{uuid.uuid4().hex}{ext}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath, "wb") as f:
            shutil.copyfileobj(prize_image.file, f)
        prize_image_url = f"/static/uploads/{fname}"

    data = {
        "title": title.strip(),
        "description": description.strip() or None,
        "share_message_template": share_message_template.strip() or None,
        "prize_image_url": prize_image_url,
        "prize_value": float(prize_value) if prize_value.strip() else None,
        "rules": rules.strip() or None,
        "goal_amount": goal_amount,
        "price_per_quota": price_per_quota,
        "max_per_person": max_per_person,
        "pix_key": pix_key.strip() or None,
        "pix_receiver_name": pix_receiver_name.strip() or "SORTEIOS",
        "pix_receiver_city": pix_receiver_city.strip() or "SAO PAULO",
        "draw_date": draw_date.strip() or None,
        "reservation_expires_minutes": reservation_expires_minutes,
    }

    if data["goal_amount"] <= 0 or data["price_per_quota"] <= 0:
        return templates.TemplateResponse(request, "admin_raffle_form.html",
                                          {"error": "Valores devem ser positivos", "campaign": None})

    campaign = crud.create_raffle(session, data)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "create_raffle", f"Sorteio '{campaign.title}' id={campaign.id}", ip)
    return RedirectResponse(f"/admin/sorteios/{campaign.id}", status_code=303)


@app.get("/admin/sorteios/{campaign_id}", response_class=HTMLResponse)
def admin_raffle_detail(request: Request, campaign_id: int,
                        session: Session = Depends(get_db), _: None = Depends(require_admin)):
    campaign = crud.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Sorteio não encontrado")
    stats = crud.get_raffle_stats(session, campaign_id)
    orders = crud.list_orders(session, campaign_id=campaign_id, limit=50)
    return templates.TemplateResponse(request, "admin_raffle_form.html", {
        "campaign": campaign,
        "stats": stats,
        "orders": orders,
    })


@app.post("/admin/sorteios/{campaign_id}/editar")
async def admin_raffle_update(
    request: Request,
    campaign_id: int,
    session: Session = Depends(get_db),
    _: None = Depends(require_admin),
    title: str = Form(...),
    description: str = Form(""),
    share_message_template: str = Form(""),
    prize_value: str = Form(""),
    rules: str = Form(""),
    max_per_person: int = Form(10),
    pix_key: str = Form(""),
    pix_receiver_name: str = Form("SORTEIOS"),
    pix_receiver_city: str = Form("SAO PAULO"),
    draw_date: str = Form(""),
    reservation_expires_minutes: int = Form(30),
    status: str = Form("active"),
    goal_amount: str = Form(""),
    prize_image: UploadFile | None = File(None),
):
    campaign = crud.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404)

    prize_image_url = campaign.prize_image_url
    if prize_image and prize_image.filename:
        ext = os.path.splitext(prize_image.filename)[-1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            fname = f"{uuid.uuid4().hex}{ext}"
            fpath = os.path.join(UPLOAD_DIR, fname)
            with open(fpath, "wb") as f:
                shutil.copyfileobj(prize_image.file, f)
            prize_image_url = f"/static/uploads/{fname}"

    data = {
        "title": title.strip(),
        "description": description.strip() or None,
        "share_message_template": share_message_template.strip() or None,
        "prize_image_url": prize_image_url,
        "prize_value": float(prize_value) if prize_value.strip() else None,
        "rules": rules.strip() or None,
        "max_per_person": max_per_person,
        "pix_key": pix_key.strip() or None,
        "pix_receiver_name": pix_receiver_name.strip() or "SORTEIOS",
        "pix_receiver_city": pix_receiver_city.strip() or "SAO PAULO",
        "draw_date": draw_date.strip() or None,
        "reservation_expires_minutes": reservation_expires_minutes,
        "status": status,
        "goal_amount": goal_amount.strip() or None,
    }
    crud.update_raffle(session, campaign_id, data)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "update_raffle", f"Sorteio id={campaign_id}", ip)
    return RedirectResponse(f"/admin/sorteios/{campaign_id}", status_code=303)


@app.post("/admin/sorteios/{campaign_id}/deletar")
def admin_raffle_delete(request: Request, campaign_id: int,
                        session: Session = Depends(get_db), _: None = Depends(require_admin)):
    ok = crud.delete_raffle(session, campaign_id)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "delete_raffle", f"Sorteio id={campaign_id}", ip)
    return RedirectResponse("/admin/sorteios", status_code=303)


@app.post("/admin/draw/{campaign_id}")
def admin_draw(campaign_id: int, request: Request,
               session: Session = Depends(get_db), _: None = Depends(require_admin)):
    chosen = crud.draw_winner(session, campaign_id)
    if not chosen:
        raise HTTPException(status_code=400, detail="Nenhuma cota para sortear")
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "draw", f"Campanha id={campaign_id} vencedor={chosen.number}", ip)
    logger.info("Draw: campaign=%s winner=%s", campaign_id, chosen.number)
    buyer_name = chosen.reserved_by
    whatsapp = None
    try:
        if chosen.order_item and chosen.order_item.order and chosen.order_item.order.buyer:
            b = chosen.order_item.order.buyer
            buyer_name = b.name
            whatsapp = b.whatsapp
    except Exception:
        pass
    return {"ok": True, "quota_id": chosen.id, "number": chosen.number,
            "reserved_by": buyer_name, "whatsapp": whatsapp}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Orders
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/pedidos", response_class=HTMLResponse)
def admin_orders_page(request: Request, session: Session = Depends(get_db),
                      _: None = Depends(require_admin),
                      campaign_id: int | None = None,
                      status: str | None = None):
    orders = crud.list_orders(session, campaign_id=campaign_id, status=status, limit=200)
    campaigns = crud.list_campaigns(session)
    # Attach numbers to orders
    orders_data = []
    for o in orders:
        nums = sorted(item.quota.number for item in o.items if item.quota)
        orders_data.append({"order": o, "numbers": nums})
    return templates.TemplateResponse(request, "admin_orders.html", {
        "orders_data": orders_data,
        "campaigns": campaigns,
        "filter_campaign": campaign_id,
        "filter_status": status,
    })


@app.post("/admin/pedidos/{order_id}/confirmar")
def admin_confirm_order(order_id: int, request: Request,
                        session: Session = Depends(get_db), _: None = Depends(require_admin)):
    order = crud.confirm_order_payment(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "confirm_payment", f"Pedido #{order_id}", ip)

    # Send confirmation email
    if order.buyer and order.buyer.email:
        numbers = sorted(item.quota.number for item in order.items if item.quota)
        html = mail.build_payment_confirmed_email(
            raffle_title=order.campaign.title if order.campaign else "",
            buyer_name=order.buyer.name,
            numbers=numbers,
            total_amount=order.total_amount,
            tracking_url=f"{BASE_URL}/pedido/{order.token}",
        )
        ok, err = mail.send_email(order.buyer.email, "Pagamento confirmado!", html)
        crud.log_email(session, order.buyer.email, "Pagamento confirmado",
                       "sent" if ok else "failed", order.id, err)

    return RedirectResponse("/admin/pedidos", status_code=303)


@app.post("/admin/pedidos/{order_id}/cancelar")
def admin_cancel_order(order_id: int, request: Request,
                       session: Session = Depends(get_db), _: None = Depends(require_admin)):
    order_orig = crud.get_order(session, order_id)
    numbers = sorted(item.quota.number for item in order_orig.items if item.quota) if order_orig else []
    order = crud.cancel_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado ou já pago")
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "cancel_order", f"Pedido #{order_id}", ip)

    if order.buyer and order.buyer.email and numbers:
        html = mail.build_cancellation_email(
            raffle_title=order.campaign.title if order.campaign else "",
            buyer_name=order.buyer.name,
            numbers=numbers,
        )
        mail.send_email(order.buyer.email, "Reserva cancelada", html)

    return RedirectResponse("/admin/pedidos", status_code=303)


@app.post("/api/admin/cancel-expired")
def api_cancel_expired(request: Request, session: Session = Depends(get_db), _: None = Depends(require_admin)):
    count = crud.cancel_expired_orders(session)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "cancel_expired", f"{count} pedidos cancelados", ip)
    return {"ok": True, "cancelled": count}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Statistics & Export
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/estatisticas", response_class=HTMLResponse)
def admin_stats_page(request: Request, session: Session = Depends(get_db),
                     _: None = Depends(require_admin),
                     campaign_id: int | None = None):
    campaigns = crud.list_campaigns(session)
    global_stats = crud.get_global_stats(session)
    raffle_stats = crud.get_raffle_stats(session, campaign_id) if campaign_id else {}
    sales_by_day = crud.get_sales_by_day(session, campaign_id)
    top_buyers = crud.get_top_buyers(session, campaign_id)
    return templates.TemplateResponse(request, "admin_stats.html", {
        "campaigns": campaigns,
        "selected_campaign_id": campaign_id,
        "global_stats": global_stats,
        "raffle_stats": raffle_stats,
        "sales_by_day": sales_by_day,
        "top_buyers": top_buyers,
    })


@app.get("/admin/exportar/csv")
def admin_export_csv(request: Request, session: Session = Depends(get_db),
                     _: None = Depends(require_admin),
                     campaign_id: int | None = None):
    csv_data = crud.export_orders_csv(session, campaign_id)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "export_csv", f"campaign_id={campaign_id}", ip)
    return StreamingResponse(
        iter([csv_data.encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pedidos.csv"},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Compradores
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/compradores", response_class=HTMLResponse)
def admin_buyers_page(request: Request, session: Session = Depends(get_db),
                      _: None = Depends(require_admin)):
    buyers = crud.list_buyers(session, limit=200)
    top = crud.get_top_buyers(session)
    return templates.TemplateResponse(request, "admin_buyers.html", {
        "buyers": buyers,
        "top_buyers": top,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Logs
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/logs", response_class=HTMLResponse)
def admin_logs_page(request: Request, session: Session = Depends(get_db),
                    _: None = Depends(require_admin)):
    admin_logs = crud.list_admin_logs(session, limit=100)
    email_logs = crud.list_email_logs(session, limit=100)
    backup_logs = crud.list_backup_logs(session, limit=50)
    return templates.TemplateResponse(request, "admin_logs.html", {
        "admin_logs": admin_logs,
        "email_logs": email_logs,
        "backup_logs": backup_logs,
    })


# ── Admin: User Management ─────────────────────────────────────────────────

@app.get("/admin/usuarios", response_class=HTMLResponse)
def admin_users_page(request: Request, session: Session = Depends(get_db),
                     _: None = Depends(require_admin)):
    current = _admin_user(request)
    current_user = crud.get_user(session, current.get("id")) if current and current.get("id") else None
    is_super_admin = _is_super_admin(current_user)
    users = crud.list_users(session)
    pending_count = sum(1 for u in users if u.status == "pending")
    return templates.TemplateResponse(request, "admin_users.html", {
        "users": users,
        "pending_count": pending_count,
        "is_super_admin": is_super_admin,
    })


@app.post("/admin/usuarios/{user_id}/aprovar")
def admin_approve_user(user_id: int, session: Session = Depends(get_db),
                       _: None = Depends(require_admin)):
    crud.update_user_status(session, user_id, "approved")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{user_id}/rejeitar")
def admin_reject_user(user_id: int, session: Session = Depends(get_db),
                       _: None = Depends(require_admin)):
    crud.update_user_status(session, user_id, "rejected")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{user_id}/limite")
def admin_set_user_limit(user_id: int, max_raffles: int = Form(...),
                         session: Session = Depends(get_db), _: None = Depends(require_admin)):
    crud.update_user_max_raffles(session, user_id, max_raffles)
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{user_id}/credenciais")
def admin_update_user_credentials(
    request: Request,
    user_id: int,
    email: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    actor_payload = _admin_user(request)
    actor_user = crud.get_user(session, actor_payload.get("id")) if actor_payload and actor_payload.get("id") else None
    if not actor_user:
        raise HTTPException(status_code=403, detail="Acesso negado")

    target = crud.get_user(session, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    new_email = (email or "").strip().lower()
    new_password = (password or "").strip()

    wants_email_change = bool(new_email and new_email != (target.email or "").strip().lower())
    wants_password_change = bool(new_password)

    if wants_password_change and len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Senha deve ter pelo menos 8 caracteres")

    if wants_email_change:
        existing = crud.get_user_by_email(session, new_email)
        if existing and existing.id != target.id:
            raise HTTPException(status_code=409, detail="E-mail já está em uso")

    if not wants_email_change and not wants_password_change:
        return RedirectResponse("/admin/usuarios", status_code=303)

    crud.update_user_credentials(
        session,
        user_id,
        email=new_email if wants_email_change else None,
        password=new_password if wants_password_change else None,
    )

    ip = _get_client_ip(request)
    changed_fields = []
    if wants_email_change:
        changed_fields.append("email")
    if wants_password_change:
        changed_fields.append("password")
    crud.log_admin_action(
        session,
        "user_credentials_update",
        f"actor={actor_user.email} target={target.email} fields={','.join(changed_fields)}",
        ip,
    )

    return RedirectResponse("/admin/usuarios", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Backup
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/backup", response_class=HTMLResponse)
def admin_backup_page(request: Request, session: Session = Depends(get_db),
                      _: None = Depends(require_admin)):
    backups = backup_service.list_backups()
    backup_logs = crud.list_backup_logs(session, limit=20)
    cloud_mode = backup_service.cloud_mode()
    cloud_configured = cloud_mode != "none"
    gdrive_ok = backup_service.gdrive_configured()
    gdrive_files = backup_service.list_gdrive_backups() if gdrive_ok else []
    return templates.TemplateResponse(request, "admin_backup.html", {
        "backups": backups,
        "backup_logs": backup_logs,
        "cloud_mode": cloud_mode,
        "cloud_configured": cloud_configured,
        "gdrive_configured": gdrive_ok,
        "gdrive_files": gdrive_files,
    })


@app.post("/admin/backup/criar")
def admin_backup_create(request: Request, session: Session = Depends(get_db),
                        _: None = Depends(require_admin)):
    result = backup_service.create_backup()
    ip = _get_client_ip(request)
    crud.log_backup(
        session,
        filename=result.get("filename") or "failed",
        size_bytes=result.get("size_bytes"),
        status="success" if not result.get("error") else "failed",
        error=result.get("error"),
    )
    crud.log_admin_action(session, "backup", f"Arquivo: {result.get('filename')}", ip)
    return RedirectResponse("/admin/backup", status_code=303)


@app.get("/admin/backup/download/{filename}")
def admin_backup_download(filename: str, session: Session = Depends(get_db),
                          _: None = Depends(require_admin)):
    fpath = backup_service.get_backup_path(filename)
    if not fpath:
        raise HTTPException(status_code=404, detail="Backup não encontrado")

    def file_iterator(path: str, chunk_size: int = 65536):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    media_type = "application/gzip" if filename.endswith(".gz") else "application/octet-stream"
    return StreamingResponse(
        file_iterator(fpath),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/admin/backup/{filename}/gdrive")
def admin_backup_upload_gdrive(filename: str, request: Request,
                               session: Session = Depends(get_db),
                               _: None = Depends(require_admin)):
    result = backup_service.upload_to_cloud(filename)
    ip = _get_client_ip(request)
    if result.get("error"):
        crud.log_admin_action(session, "backup_cloud_error",
                              f"Arquivo: {filename} — {result['error']}", ip)
    else:
        detail = f"Arquivo: {filename} enviado para nuvem via {result.get('mode', 'unknown')}"
        if result.get("file_id"):
            detail += f" (id={result.get('file_id')})"
        if result.get("status_code"):
            detail += f" (status={result.get('status_code')})"
        crud.log_admin_action(session, "backup_cloud", detail, ip)
    return RedirectResponse("/admin/backup", status_code=303)


@app.post("/admin/backup/criar-gdrive")
def admin_backup_create_and_upload(request: Request,
                                   session: Session = Depends(get_db),
                                   _: None = Depends(require_admin)):
    result = backup_service.create_backup()
    ip = _get_client_ip(request)
    crud.log_backup(
        session,
        filename=result.get("filename") or "failed",
        size_bytes=result.get("size_bytes"),
        status="success" if not result.get("error") else "failed",
        error=result.get("error"),
    )
    if result.get("filename") and not result.get("error"):
        cloud_result = backup_service.upload_to_cloud(result["filename"])
        detail = (f"Arquivo: {result['filename']} — Nuvem({cloud_result.get('mode', 'none')}): "
                  + ("ok" if not cloud_result.get("error")
                     else "erro " + cloud_result.get("error", "")))
        crud.log_admin_action(session, "backup_cloud", detail, ip)
    return RedirectResponse("/admin/backup", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Settings
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/configuracoes", response_class=HTMLResponse)
def admin_settings_page(request: Request, _: None = Depends(require_admin)):
    current = {
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": os.getenv("SMTP_PORT", "587"),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_from": os.getenv("SMTP_FROM", ""),
        "smtp_from_name": os.getenv("SMTP_FROM_NAME", "Sorteios"),
        "admin_email": os.getenv("ADMIN_EMAIL", ""),
        "base_url": os.getenv("BASE_URL", "http://localhost:8000"),
    }
    return templates.TemplateResponse(request, "admin_settings.html", {"settings": current})


@app.post("/admin/configuracoes")
def admin_settings_save(request: Request, session: Session = Depends(get_db),
                        _: None = Depends(require_admin)):
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "settings_update", "Configurações atualizadas pelo admin", ip)
    return templates.TemplateResponse(request, "admin_settings.html", {
        "settings": {},
        "success": "Configurações salvas. Reinicie o servidor para aplicar variáveis de ambiente.",
    })


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — Resend Email
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/pedidos/{order_id}/reenviar-email")
def admin_resend_email(order_id: int, request: Request,
                       session: Session = Depends(get_db), _: None = Depends(require_admin)):
    order = crud.get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404)
    if not (order.buyer and order.buyer.email):
        raise HTTPException(status_code=400, detail="Comprador sem e-mail cadastrado")

    numbers = sorted(item.quota.number for item in order.items if item.quota)
    expires_str = order.expires_at.strftime("%d/%m/%Y %H:%M") if order.expires_at else "—"

    html = mail.build_order_confirmation_email(
        order_token=order.token,
        raffle_title=order.campaign.title if order.campaign else "",
        buyer_name=order.buyer.name,
        numbers=numbers,
        total_amount=order.total_amount,
        pix_payload=order.pix_payload,
        expires_at=expires_str,
        tracking_url=f"{BASE_URL}/pedido/{order.token}",
        has_qr=bool(order.qr_code_base64),
    )
    ok, err = mail.send_email(order.buyer.email, "Reenvio — sua reserva", html, order.qr_code_base64)
    crud.log_email(session, order.buyer.email, "Reenvio", "sent" if ok else "failed", order.id, err)
    ip = _get_client_ip(request)
    crud.log_admin_action(session, "resend_email", f"Pedido #{order_id}", ip)
    return {"ok": ok, "error": err}
