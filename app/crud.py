from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, String
from . import models
import math
import datetime
import random
import uuid
import secrets
import csv
import io
import logging

logger = logging.getLogger(__name__)


# ─── Campaigns ────────────────────────────────────────────────────────────────

def create_campaign(db: Session, title: str, goal_amount: float, price_per_quota: float,
                    pix_key: str | None, draw_date: str | None = None):
    slug = uuid.uuid4().hex[:8]
    dt = _parse_date(draw_date)
    campaign = models.Campaign(
        title=title, slug=slug, goal_amount=goal_amount,
        price_per_quota=price_per_quota, pix_key=pix_key, draw_date=dt,
    )
    db.add(campaign)
    db.flush()
    total_quotas = int(math.floor(goal_amount / price_per_quota))
    db.add_all([
        models.Quota(campaign_id=campaign.id, number=i, status="available")
        for i in range(1, total_quotas + 1)
    ])
    db.commit()
    db.refresh(campaign)
    return campaign


def create_raffle(db: Session, data: dict) -> models.Campaign:
    """Cria sorteio com campos completos."""
    draw_date = _parse_date(data.get("draw_date"))
    goal = float(data["goal_amount"])
    price = float(data["price_per_quota"])
    slug = uuid.uuid4().hex[:8]

    campaign = models.Campaign(
        title=data["title"],
        slug=slug,
        goal_amount=goal,
        price_per_quota=price,
        draw_date=draw_date,
        description=data.get("description"),
        prize_image_url=data.get("prize_image_url"),
        prize_value=data.get("prize_value"),
        rules=data.get("rules"),
        max_per_person=data.get("max_per_person", 10),
        pix_key=data.get("pix_key"),
        pix_receiver_name=(data.get("pix_receiver_name") or "SORTEIOS")[:25].upper(),
        pix_receiver_city=(data.get("pix_receiver_city") or "SAO PAULO")[:15].upper(),
        reservation_expires_minutes=data.get("reservation_expires_minutes", 30),
        owner_id=data.get("owner_id"),
    )
    db.add(campaign)
    db.flush()
    total_quotas = int(math.floor(goal / price))
    db.add_all([
        models.Quota(campaign_id=campaign.id, number=i, status="available")
        for i in range(1, total_quotas + 1)
    ])
    db.commit()
    db.refresh(campaign)
    return campaign


def update_raffle(db: Session, campaign_id: int, data: dict) -> models.Campaign | None:
    c = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not c:
        return None
    allowed = [
        "title", "description", "prize_image_url", "prize_value", "rules",
        "max_per_person", "pix_key", "pix_receiver_name", "pix_receiver_city",
        "reservation_expires_minutes", "status",
    ]
    for field in allowed:
        if field in data and data[field] is not None:
            setattr(c, field, data[field])
    if "draw_date" in data:
        c.draw_date = _parse_date(data["draw_date"])

    # ── Expand quota pool when goal_amount increases ──────────────────
    if "goal_amount" in data and data["goal_amount"]:
        new_goal = float(data["goal_amount"])
        if new_goal > c.goal_amount:
            new_total = int(math.floor(new_goal / c.price_per_quota))
            current_max = (
                db.query(func.max(models.Quota.number))
                .filter(models.Quota.campaign_id == campaign_id)
                .scalar()
            ) or 0
            if new_total > current_max:
                db.bulk_save_objects([
                    models.Quota(campaign_id=campaign_id, number=i, status="available")
                    for i in range(current_max + 1, new_total + 1)
                ])
            c.goal_amount = new_goal

    db.commit()
    db.refresh(c)
    return c


def delete_raffle(db: Session, campaign_id: int) -> bool:
    c = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not c:
        return False
    db.delete(c)
    db.commit()
    return True


def draw_winner(db: Session, campaign_id: int):
    camp = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not camp:
        return None
    for filters in [
        [models.Quota.paid == True],
        [models.Quota.reserved_by != None],
        [],
    ]:
        qs = db.query(models.Quota).filter(
            models.Quota.campaign_id == campaign_id, *filters
        ).all()
        if qs:
            chosen = random.choice(qs)
            camp.winner_quota_id = chosen.id
            camp.status = "drawn"
            db.commit()
            return chosen
    return None


def get_campaign(db: Session, campaign_id: int) -> models.Campaign | None:
    return db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()


def get_campaign_by_slug(db: Session, slug: str) -> models.Campaign | None:
    return db.query(models.Campaign).filter(models.Campaign.slug == slug).first()


def list_campaigns(db: Session):
    return db.query(models.Campaign).order_by(models.Campaign.created_at.desc()).all()


# ─── Quotas ───────────────────────────────────────────────────────────────────

def list_quotas(db: Session, campaign_id: int):
    return (
        db.query(models.Quota)
        .filter(models.Quota.campaign_id == campaign_id)
        .order_by(models.Quota.number)
        .all()
    )


def reserve_quota(db: Session, campaign_id: int, number: int, buyer: str):
    """Legacy: reserve single quota (keeps backward compat)."""
    q = (
        db.query(models.Quota)
        .filter(models.Quota.campaign_id == campaign_id, models.Quota.number == number)
        .with_for_update()
        .first()
    )
    if not q or q.reserved_by:
        return None
    q.reserved_by = buyer
    q.reserved_at = datetime.datetime.utcnow()
    q.status = "reserved"
    db.commit()
    db.refresh(q)
    return q


def mark_paid(db: Session, quota_ids: list[int]):
    qs = db.query(models.Quota).filter(models.Quota.id.in_(quota_ids)).all()
    for q in qs:
        q.paid = True
        q.status = "paid"
    db.commit()
    return qs


def get_campaign_stats(db: Session, campaign_id: int) -> dict:
    total = db.query(func.count(models.Quota.id)).filter(models.Quota.campaign_id == campaign_id).scalar() or 0
    sold = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id, models.Quota.reserved_by != None
    ).scalar() or 0
    paid = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id, models.Quota.paid == True
    ).scalar() or 0
    return {"total": total, "reserved": sold, "paid": paid}


# ─── Atomic Checkout (core) ───────────────────────────────────────────────────

def checkout_atomic(
    db: Session,
    campaign_id: int,
    numbers: list[int],
    buyer_name: str,
    buyer_whatsapp: str,
    buyer_email: str | None = None,
    buyer_cpf: str | None = None,
) -> dict:
    """
    Reserva atomicamente todos os números selecionados e cria um pedido.
    Usa row-level locking para evitar duplicidade.
    Retorna {"order": Order, "error": str|None}
    """
    from .pix import generate_pix_payload
    import qrcode
    import base64
    from io import BytesIO

    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        return {"order": None, "error": "Sorteio não encontrado"}
    if campaign.status not in ("active",):
        return {"order": None, "error": "Sorteio não está ativo"}

    # Validate max_per_person
    max_pp = campaign.max_per_person or 10
    if len(numbers) > max_pp:
        return {"order": None, "error": f"Máximo de {max_pp} números por pessoa"}

    # Lock all requested quotas atomically
    quotas = (
        db.query(models.Quota)
        .filter(
            models.Quota.campaign_id == campaign_id,
            models.Quota.number.in_(numbers),
        )
        .with_for_update()
        .all()
    )

    if len(quotas) != len(numbers):
        return {"order": None, "error": "Um ou mais números inválidos para este sorteio"}

    # Check all are available
    unavailable = [q.number for q in quotas if q.status not in ("available",)]
    if unavailable:
        return {"order": None, "error": f"Números indisponíveis: {', '.join(map(str, unavailable))}"}

    # Create or find buyer
    buyer = _get_or_create_buyer(db, buyer_name, buyer_whatsapp, buyer_email, buyer_cpf)

    # Expiration
    expires_min = campaign.reservation_expires_minutes or 30
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_min)

    # Total amount
    total = len(numbers) * campaign.price_per_quota

    # Generate unique token
    token = secrets.token_urlsafe(32)

    # Create order
    order = models.Order(
        campaign_id=campaign_id,
        buyer_id=buyer.id,
        token=token,
        status="pending",
        total_amount=total,
        expires_at=expires_at,
    )
    db.add(order)
    db.flush()

    # Reserve quotas and create order items
    now = datetime.datetime.utcnow()
    for q in quotas:
        q.reserved_by = buyer_name
        q.reserved_at = now
        q.status = "reserved"
        item = models.OrderItem(order_id=order.id, quota_id=q.id)
        db.add(item)

    db.flush()

    # Generate PIX payload
    pix_payload = None
    qr_b64 = None
    try:
        if campaign.pix_key:
            txid = f"ORD{order.id:06d}"[:25]
            # Descrição exibida pelo banco ao comprador: título + nome do comprador
            desc = f"{campaign.title} - {buyer_name}"[:99]
            pix_payload = generate_pix_payload(
                key=campaign.pix_key,
                amount=total,
                description=desc,
                txid=txid,
                merchant_name=(campaign.pix_receiver_name or "SORTEIOS")[:25],
                merchant_city=(campaign.pix_receiver_city or "SAO PAULO")[:15],
            )
            img = qrcode.make(pix_payload)
            buf = BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode()
            order.pix_payload = pix_payload
            order.qr_code_base64 = qr_b64
    except Exception as e:
        logger.warning("PIX generation error: %s", e)

    db.commit()
    db.refresh(order)

    return {"order": order, "error": None}


def _get_or_create_buyer(
    db: Session, name: str, whatsapp: str,
    email: str | None = None, cpf: str | None = None,
) -> models.Buyer:
    buyer = db.query(models.Buyer).filter(models.Buyer.whatsapp == whatsapp).first()
    if not buyer:
        buyer = models.Buyer(name=name, whatsapp=whatsapp, email=email, cpf=cpf)
        db.add(buyer)
        db.flush()
    else:
        # Update name/email if changed
        buyer.name = name
        if email:
            buyer.email = email
    return buyer


# ─── Order management ─────────────────────────────────────────────────────────

def get_order_by_token(db: Session, token: str) -> models.Order | None:
    return db.query(models.Order).filter(models.Order.token == token).first()


def get_order(db: Session, order_id: int) -> models.Order | None:
    return db.query(models.Order).filter(models.Order.id == order_id).first()


def confirm_order_payment(db: Session, order_id: int) -> models.Order | None:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None
    order.status = "paid"
    order.paid_at = datetime.datetime.utcnow()
    for item in order.items:
        item.quota.paid = True
        item.quota.status = "paid"
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int, reason: str = "manual") -> models.Order | None:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order or order.status in ("paid",):
        return None
    order.status = "cancelled"
    order.cancelled_at = datetime.datetime.utcnow()
    for item in order.items:
        q = item.quota
        q.reserved_by = None
        q.reserved_at = None
        q.paid = False
        q.status = "available"
    db.commit()
    db.refresh(order)
    return order


def cancel_expired_orders(db: Session) -> int:
    """Cancela pedidos pendentes expirados. Retorna a quantidade cancelada."""
    now = datetime.datetime.utcnow()
    expired = (
        db.query(models.Order)
        .filter(models.Order.status == "pending", models.Order.expires_at < now)
        .all()
    )
    count = 0
    for order in expired:
        order.status = "expired"
        order.cancelled_at = now
        for item in order.items:
            q = item.quota
            if q.status == "reserved":
                q.reserved_by = None
                q.reserved_at = None
                q.paid = False
                q.status = "available"
        count += 1
    if count:
        db.commit()
    return count


def list_orders(
    db: Session,
    campaign_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    q = db.query(models.Order)
    if campaign_id:
        q = q.filter(models.Order.campaign_id == campaign_id)
    if status:
        q = q.filter(models.Order.status == status)
    return q.order_by(desc(models.Order.created_at)).offset(offset).limit(limit).all()


def list_buyers(db: Session, limit: int = 100, offset: int = 0):
    return (
        db.query(models.Buyer)
        .order_by(desc(models.Buyer.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )


# ─── Statistics ───────────────────────────────────────────────────────────────

def get_raffle_stats(db: Session, campaign_id: int) -> dict:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        return {}

    total = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id
    ).scalar() or 0

    available = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id,
        models.Quota.status == "available",
    ).scalar() or 0

    reserved = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id,
        models.Quota.status == "reserved",
    ).scalar() or 0

    paid = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id,
        models.Quota.paid == True,
    ).scalar() or 0

    cancelled = db.query(func.count(models.Quota.id)).filter(
        models.Quota.campaign_id == campaign_id,
        models.Quota.status == "cancelled",
    ).scalar() or 0

    revenue_paid = paid * campaign.price_per_quota
    revenue_pending = reserved * campaign.price_per_quota
    conversion = (paid / total * 100) if total > 0 else 0.0

    return {
        "total": total,
        "available": available,
        "reserved": reserved,
        "paid": paid,
        "cancelled": cancelled,
        "revenue_paid": revenue_paid,
        "revenue_pending": revenue_pending,
        "conversion_rate": round(conversion, 1),
    }


def get_global_stats(db: Session) -> dict:
    total_campaigns = db.query(func.count(models.Campaign.id)).scalar() or 0
    total_orders = db.query(func.count(models.Order.id)).scalar() or 0
    total_paid_orders = db.query(func.count(models.Order.id)).filter(
        models.Order.status == "paid"
    ).scalar() or 0
    total_revenue = db.query(func.sum(models.Order.total_amount)).filter(
        models.Order.status == "paid"
    ).scalar() or 0.0
    total_pending = db.query(func.sum(models.Order.total_amount)).filter(
        models.Order.status == "pending"
    ).scalar() or 0.0
    total_buyers = db.query(func.count(models.Buyer.id)).scalar() or 0

    return {
        "total_campaigns": total_campaigns,
        "total_orders": total_orders,
        "total_paid_orders": total_paid_orders,
        "total_revenue": round(total_revenue, 2),
        "total_pending": round(total_pending, 2),
        "total_buyers": total_buyers,
    }


def get_sales_by_day(db: Session, campaign_id: int | None = None) -> list[dict]:
    """Retorna contagem de pedidos pagos por dia (últimos 30 dias)."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    # Normalize date to string to avoid DB-driver specific date coercion issues.
    day_col = cast(func.date(models.Order.created_at), String)
    q = (
        db.query(
            day_col.label("day"),
            func.count(models.Order.id).label("count"),
            func.sum(models.Order.total_amount).label("revenue"),
        )
        .filter(models.Order.status == "paid", models.Order.created_at >= cutoff)
    )
    if campaign_id:
        q = q.filter(models.Order.campaign_id == campaign_id)
    rows = q.group_by(day_col).order_by(day_col).all()
    return [{"day": str(r.day), "count": r.count, "revenue": float(r.revenue or 0)} for r in rows]


def get_top_buyers(db: Session, campaign_id: int | None = None, limit: int = 10) -> list[dict]:
    total_spent = func.sum(models.Order.total_amount)
    q = (
        db.query(
            models.Buyer.name,
            models.Buyer.whatsapp,
            func.count(models.Order.id).label("orders"),
            total_spent.label("total"),
        )
        .join(models.Order, models.Order.buyer_id == models.Buyer.id)
        .filter(models.Order.status == "paid")
    )
    if campaign_id:
        q = q.filter(models.Order.campaign_id == campaign_id)
    rows = q.group_by(models.Buyer.id).order_by(desc(total_spent)).limit(limit).all()
    return [
        {"name": r.name, "whatsapp": r.whatsapp, "orders": r.orders, "total": float(r.total or 0)}
        for r in rows
    ]


# ─── CSV Export ───────────────────────────────────────────────────────────────

def export_orders_csv(db: Session, campaign_id: int | None = None) -> str:
    orders = list_orders(db, campaign_id=campaign_id, limit=10000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ID", "Token", "Status", "Comprador", "WhatsApp", "E-mail",
        "Números", "Total (R$)", "Criado em", "Pago em",
    ])
    for o in orders:
        nums = ",".join(str(item.quota.number) for item in o.items if item.quota)
        writer.writerow([
            o.id, o.token, o.status,
            o.buyer.name if o.buyer else "",
            o.buyer.whatsapp if o.buyer else "",
            o.buyer.email if o.buyer else "",
            nums,
            f"{o.total_amount:.2f}",
            o.created_at.strftime("%d/%m/%Y %H:%M") if o.created_at else "",
            o.paid_at.strftime("%d/%m/%Y %H:%M") if o.paid_at else "",
        ])
    return buf.getvalue()


# ─── Logs ─────────────────────────────────────────────────────────────────────

def log_admin_action(db: Session, action: str, details: str | None = None, ip: str | None = None):
    entry = models.AdminLog(action=action, details=details, ip_address=ip)
    db.add(entry)
    db.commit()


def log_email(
    db: Session,
    recipient: str,
    subject: str,
    status: str,
    order_id: int | None = None,
    error: str | None = None,
):
    entry = models.EmailLog(
        order_id=order_id,
        recipient=recipient,
        subject=subject,
        status=status,
        error=error,
    )
    db.add(entry)
    db.commit()


def log_backup(db: Session, filename: str, size_bytes: int | None, status: str, error: str | None = None):
    entry = models.BackupLog(filename=filename, size_bytes=size_bytes, status=status, error=error)
    db.add(entry)
    db.commit()


def list_admin_logs(db: Session, limit: int = 100) -> list[models.AdminLog]:
    return db.query(models.AdminLog).order_by(desc(models.AdminLog.created_at)).limit(limit).all()


def list_email_logs(db: Session, limit: int = 100) -> list[models.EmailLog]:
    return db.query(models.EmailLog).order_by(desc(models.EmailLog.created_at)).limit(limit).all()


def list_backup_logs(db: Session, limit: int = 50) -> list[models.BackupLog]:
    return db.query(models.BackupLog).order_by(desc(models.BackupLog.created_at)).limit(limit).all()


# ─── Users ────────────────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email.lower().strip()).first()

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, email: str, name: str, company_name: str | None,
                phone: str | None, password_hash: str):
    user = models.User(
        email=email.lower().strip(),
        name=name.strip(),
        company_name=company_name.strip() if company_name else None,
        phone=phone.strip() if phone else None,
        password_hash=password_hash,
        status="pending",
        role="organizer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def list_users(db: Session, status: str | None = None):
    q = db.query(models.User)
    if status:
        q = q.filter(models.User.status == status)
    return q.order_by(models.User.created_at.desc()).all()

def update_user_status(db: Session, user_id: int, status: str):
    user = get_user(db, user_id)
    if user:
        user.status = status
        db.commit()
        db.refresh(user)
    return user

def update_user_max_raffles(db: Session, user_id: int, max_raffles: int):
    user = get_user(db, user_id)
    if user:
        user.max_raffles = max_raffles
        db.commit()
        db.refresh(user)
    return user

def update_user_credentials(
    db: Session,
    user_id: int,
    email: str | None = None,
    password: str | None = None,
):
    from .auth import hash_password

    user = get_user(db, user_id)
    if not user:
        return None

    if email is not None:
        user.email = email.lower().strip()

    if password:
        user.password_hash = hash_password(password)

    db.commit()
    db.refresh(user)
    return user

def count_user_raffles(db: Session, owner_id: int) -> int:
    return db.query(models.Campaign).filter(models.Campaign.owner_id == owner_id).count()

def list_campaigns_by_owner(db: Session, owner_id: int):
    return db.query(models.Campaign).filter(
        models.Campaign.owner_id == owner_id
    ).order_by(models.Campaign.created_at.desc()).all()

def list_orders_by_campaign(db: Session, campaign_id: int, limit: int = 50):
    return (db.query(models.Order)
            .filter(models.Order.campaign_id == campaign_id)
            .order_by(models.Order.created_at.desc())
            .limit(limit).all())


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(draw_date: str | None) -> datetime.datetime | None:
    if not draw_date:
        return None
    try:
        return datetime.datetime.fromisoformat(draw_date)
    except Exception:
        return None
