from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey,
    DateTime, UniqueConstraint, Index, Text,
)
from sqlalchemy.orm import relationship
from .db import Base
import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    company_name = Column(String(200), nullable=True)
    phone = Column(String(30), nullable=True)
    password_hash = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending|approved|rejected
    role = Column(String(20), nullable=False, default="organizer")  # organizer|admin
    max_raffles = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    campaigns = relationship("Campaign", back_populates="owner", foreign_keys="Campaign.owner_id")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(16), unique=True, nullable=False, index=True)
    draw_date = Column(DateTime, nullable=True)
    goal_amount = Column(Float, nullable=False)
    price_per_quota = Column(Float, nullable=False)
    pix_key = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active | drawn | closed | sold_out
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    winner_quota_id = Column(Integer, ForeignKey("quotas.id", use_alter=True), nullable=True)

    # Enhanced fields
    description = Column(Text, nullable=True)
    prize_image_url = Column(String(500), nullable=True)
    prize_value = Column(Float, nullable=True)
    rules = Column(Text, nullable=True)
    share_message_template = Column(Text, nullable=True)
    max_per_person = Column(Integer, default=10, nullable=True)
    pix_receiver_name = Column(String(25), default="SORTEIOS", nullable=True)
    pix_receiver_city = Column(String(15), default="SAO PAULO", nullable=True)
    reservation_expires_minutes = Column(Integer, default=30, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner = relationship("User", back_populates="campaigns", foreign_keys=[owner_id])

    quotas = relationship(
        "Quota",
        primaryjoin="Campaign.id == Quota.campaign_id",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="select",
    )
    orders = relationship("Order", back_populates="campaign", cascade="all, delete-orphan")


class Quota(Base):
    __tablename__ = "quotas"
    __table_args__ = (
        UniqueConstraint("campaign_id", "number", name="uq_campaign_number"),
        Index("ix_quota_campaign_paid", "campaign_id", "paid"),
        Index("ix_quota_campaign_status", "campaign_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    reserved_by = Column(String(200), nullable=True)
    reserved_at = Column(DateTime, nullable=True)
    paid = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="available", nullable=False)  # available|reserved|paid|cancelled|blocked

    campaign = relationship("Campaign", back_populates="quotas", foreign_keys=[campaign_id])
    order_item = relationship("OrderItem", back_populates="quota", uselist=False)


class Buyer(Base):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    whatsapp = Column(String(20), nullable=True, index=True)
    email = Column(String(200), nullable=True, index=True)
    cpf = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    orders = relationship("Order", back_populates="buyer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending|paid|cancelled|expired
    total_amount = Column(Float, nullable=False, default=0.0)
    pix_payload = Column(Text, nullable=True)
    qr_code_base64 = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    campaign = relationship("Campaign", back_populates="orders")
    buyer = relationship("Buyer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    email_logs = relationship("EmailLog", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    quota_id = Column(Integer, ForeignKey("quotas.id"), nullable=False)

    order = relationship("Order", back_populates="items")
    quota = relationship("Quota", back_populates="order_item")


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    recipient = Column(String(200), nullable=True)
    subject = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="sent")  # sent|failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    order = relationship("Order", back_populates="email_logs")


class BackupLog(Base):
    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(200), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="success")  # success|failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
