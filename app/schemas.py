from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
import re


# ─── Quota ────────────────────────────────────────────────────────────────────

class QuotaOut(BaseModel):
    id: int
    number: int
    reserved_by: Optional[str] = None
    paid: bool
    status: str = "available"

    model_config = {"from_attributes": True}


# ─── Campaign / Raffle ────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    title: str
    goal_amount: float
    price_per_quota: float
    pix_key: Optional[str] = None
    draw_date: Optional[str] = None
    share_message_template: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Título não pode ser vazio")
        return v[:200]


class RaffleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    share_message_template: Optional[str] = None
    prize_image_url: Optional[str] = None
    prize_value: Optional[float] = None
    rules: Optional[str] = None
    goal_amount: float
    price_per_quota: float
    max_per_person: int = 10
    pix_key: Optional[str] = None
    pix_receiver_name: str = "SORTEIOS"
    pix_receiver_city: str = "SAO PAULO"
    draw_date: Optional[str] = None
    reservation_expires_minutes: int = 30

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Título não pode ser vazio")
        return v[:200]

    @field_validator("pix_receiver_name")
    @classmethod
    def clean_receiver_name(cls, v: str) -> str:
        return v.strip()[:25].upper()

    @field_validator("pix_receiver_city")
    @classmethod
    def clean_receiver_city(cls, v: str) -> str:
        return v.strip()[:15].upper()


class RaffleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    share_message_template: Optional[str] = None
    prize_image_url: Optional[str] = None
    prize_value: Optional[float] = None
    rules: Optional[str] = None
    max_per_person: Optional[int] = None
    pix_key: Optional[str] = None
    pix_receiver_name: Optional[str] = None
    pix_receiver_city: Optional[str] = None
    draw_date: Optional[str] = None
    reservation_expires_minutes: Optional[int] = None
    status: Optional[str] = None


class CampaignSummary(BaseModel):
    id: int
    title: str
    slug: str
    draw_date: Optional[datetime] = None
    goal_amount: float
    price_per_quota: float
    pix_key: Optional[str] = None
    status: str
    winner_quota_id: Optional[int] = None
    created_at: Optional[datetime] = None
    description: Optional[str] = None
    share_message_template: Optional[str] = None
    prize_image_url: Optional[str] = None
    prize_value: Optional[float] = None
    rules: Optional[str] = None
    max_per_person: Optional[int] = None
    pix_receiver_name: Optional[str] = None
    pix_receiver_city: Optional[str] = None
    reservation_expires_minutes: Optional[int] = None

    model_config = {"from_attributes": True}


class Campaign(CampaignSummary):
    quotas: List[QuotaOut] = []


# ─── Buyer ────────────────────────────────────────────────────────────────────

class BuyerIn(BaseModel):
    name: str
    whatsapp: str
    email: Optional[str] = None
    cpf: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome é obrigatório")
        return v[:200]

    @field_validator("whatsapp")
    @classmethod
    def whatsapp_valid(cls, v: str) -> str:
        v = re.sub(r"\D", "", v)
        if len(v) < 10:
            raise ValueError("WhatsApp inválido")
        return v[:20]

    @field_validator("cpf")
    @classmethod
    def cpf_clean(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        return re.sub(r"\D", "", v)[:20]


class BuyerOut(BaseModel):
    id: int
    name: str
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    cpf: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Order / Checkout ─────────────────────────────────────────────────────────

class CheckoutIn(BaseModel):
    campaign_id: int
    numbers: List[int]
    buyer: BuyerIn

    @field_validator("numbers")
    @classmethod
    def numbers_not_empty(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("Selecione ao menos um número")
        if len(v) > 200:
            raise ValueError("Máximo de 200 números por pedido")
        return sorted(set(v))


class OrderItemOut(BaseModel):
    id: int
    quota_id: int
    number: Optional[int] = None

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    token: str
    status: str
    total_amount: float
    pix_payload: Optional[str] = None
    qr_code_base64: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    buyer: Optional[BuyerOut] = None
    campaign: Optional[CampaignSummary] = None
    numbers: List[int] = []

    model_config = {"from_attributes": True}


# ─── Stats ────────────────────────────────────────────────────────────────────

class CampaignStats(BaseModel):
    total: int
    reserved: int
    paid: int
    available: int
    cancelled: int
    revenue_paid: float
    revenue_pending: float
    conversion_rate: float


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminLogOut(BaseModel):
    id: int
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmailLogOut(BaseModel):
    id: int
    order_id: Optional[int] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    status: str
    error: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BackupLogOut(BaseModel):
    id: int
    filename: str
    size_bytes: Optional[int] = None
    status: str
    error: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SettingsIn(BaseModel):
    pix_key: Optional[str] = None
    pix_receiver_name: Optional[str] = None
    pix_receiver_city: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_from_name: Optional[str] = None
    admin_email: Optional[str] = None
