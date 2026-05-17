"""Serviço de envio de e-mail via SMTP com templates HTML."""
import smtplib
import ssl
import base64
import os
import logging
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Sorteios")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and SMTP_FROM)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    qr_code_base64: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> tuple[bool, str | None]:
    """Envia e-mail HTML. Retorna (sucesso, erro|None)."""
    if not is_configured():
        logger.warning("E-mail não configurado, ignorando envio para %s", to)
        return False, "E-mail não configurado"

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
    msg["To"] = to

    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)
    alternative.attach(MIMEText(html_body, "html", "utf-8"))

    if qr_code_base64:
        try:
            qr_data = base64.b64decode(qr_code_base64)
            img_part = MIMEImage(qr_data, "png")
            img_part.add_header("Content-ID", "<qrcode>")
            img_part.add_header("Content-Disposition", "inline", filename="qrcode.png")
            msg.attach(img_part)
        except Exception as e:
            logger.warning("Erro ao anexar QR code: %s", e)

    for filepath, filename in attachments or []:
        try:
            with open(filepath, "rb") as fh:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(fh.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
        except Exception as e:
            logger.warning("Erro ao anexar arquivo %s: %s", filename, e)
            return False, f"Erro ao anexar arquivo {filename}: {e}"

    try:
        ctx = ssl.create_default_context()
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, to, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, to, msg.as_string())
        logger.info("E-mail enviado para %s: %s", to, subject)
        return True, None
    except Exception as e:
        err = str(e)
        logger.error("Falha ao enviar e-mail para %s: %s", to, err)
        return False, err


# ─── Templates ────────────────────────────────────────────────────────────────

def _base_template(content: str, title: str = "Sorteios") -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#0f1724;font-family:'Segoe UI',Arial,sans-serif;color:#e6eef6;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f1724;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <!-- Header -->
        <tr><td style="background:linear-gradient(90deg,#7c3aed,#06b6d4);border-radius:12px 12px 0 0;padding:28px 32px;text-align:center;">
          <h1 style="margin:0;color:#fff;font-size:26px;letter-spacing:-0.5px;">🎟️ Sorteios</h1>
        </td></tr>
        <!-- Body -->
        <tr><td style="background:#081228;padding:32px;border-left:1px solid rgba(255,255,255,0.05);border-right:1px solid rgba(255,255,255,0.05);">
          {content}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#050e1f;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center;border:1px solid rgba(255,255,255,0.05);border-top:none;">
          <p style="margin:0;color:#4a5568;font-size:12px;">
            Este e-mail foi enviado automaticamente. Em caso de dúvidas, entre em contato com o organizador.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_order_confirmation_email(
    order_token: str,
    raffle_title: str,
    buyer_name: str,
    numbers: list[int],
    total_amount: float,
    pix_payload: str | None,
    expires_at: str,
    tracking_url: str,
    has_qr: bool = False,
) -> str:
    nums_html = "".join(
        f'<span style="display:inline-block;background:linear-gradient(90deg,#7c3aed,#06b6d4);color:#fff;font-weight:700;padding:6px 12px;border-radius:6px;margin:3px;font-size:15px;">{n}</span>'
        for n in sorted(numbers)
    )
    pix_section = ""
    if pix_payload:
        qr_img = '<img src="cid:qrcode" alt="QR Code PIX" style="width:200px;height:200px;border-radius:8px;" />' if has_qr else ""
        pix_section = f"""
        <div style="background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.2);border-radius:10px;padding:20px;margin:24px 0;text-align:center;">
          <h3 style="margin:0 0 16px;color:#06b6d4;font-size:18px;">💳 Pague com PIX</h3>
          {qr_img}
          <p style="margin:12px 0 8px;color:#9aa4b2;font-size:13px;">Ou copie o código PIX abaixo:</p>
          <div style="background:#050e1f;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:12px;word-break:break-all;font-family:monospace;font-size:11px;color:#a0aec0;">{pix_payload}</div>
          <p style="margin:12px 0 0;color:#f87171;font-size:13px;">⏱️ Reserva expira em: <strong style="color:#fbbf24;">{expires_at}</strong></p>
        </div>"""

    content = f"""
      <h2 style="margin:0 0 8px;color:#e6eef6;font-size:22px;">Olá, {buyer_name}! 🎉</h2>
      <p style="color:#9aa4b2;margin:0 0 24px;">Sua reserva no sorteio <strong style="color:#a78bfa;">{raffle_title}</strong> foi realizada com sucesso!</p>

      <div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);border-radius:10px;padding:20px;margin-bottom:24px;">
        <h3 style="margin:0 0 12px;color:#a78bfa;font-size:16px;">🎫 Seus números:</h3>
        <div style="line-height:2;">{nums_html}</div>
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);">
          <p style="margin:0;color:#9aa4b2;font-size:14px;">Total: <strong style="color:#34d399;font-size:18px;">R$ {total_amount:.2f}</strong></p>
        </div>
      </div>

      {pix_section}

      <div style="text-align:center;margin:24px 0;">
        <a href="{tracking_url}" style="display:inline-block;background:linear-gradient(90deg,#7c3aed,#06b6d4);color:#fff;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px;">
          Acompanhar Meu Pedido →
        </a>
      </div>

      <p style="color:#4a5568;font-size:12px;text-align:center;">
        Código do pedido: <code style="background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:4px;">{order_token[:16]}...</code>
      </p>
    """
    return _base_template(content, f"Confirmação - {raffle_title}")


def build_payment_confirmed_email(
    raffle_title: str,
    buyer_name: str,
    numbers: list[int],
    total_amount: float,
    tracking_url: str,
) -> str:
    nums_html = "".join(
        f'<span style="display:inline-block;background:#065f46;color:#34d399;font-weight:700;padding:6px 12px;border-radius:6px;margin:3px;font-size:15px;">{n}</span>'
        for n in sorted(numbers)
    )
    content = f"""
      <h2 style="margin:0 0 8px;color:#34d399;font-size:22px;">✅ Pagamento Confirmado!</h2>
      <p style="color:#9aa4b2;margin:0 0 24px;">
        Parabéns, <strong style="color:#e6eef6;">{buyer_name}</strong>!
        Seu pagamento no sorteio <strong style="color:#a78bfa;">{raffle_title}</strong> foi confirmado.
      </p>
      <div style="background:rgba(52,211,153,0.08);border:1px solid rgba(52,211,153,0.2);border-radius:10px;padding:20px;margin-bottom:24px;">
        <h3 style="margin:0 0 12px;color:#34d399;">🎫 Seus números confirmados:</h3>
        <div style="line-height:2;">{nums_html}</div>
        <p style="margin:16px 0 0;color:#9aa4b2;font-size:14px;">
          Total pago: <strong style="color:#34d399;">R$ {total_amount:.2f}</strong>
        </p>
      </div>
      <div style="text-align:center;">
        <a href="{tracking_url}" style="display:inline-block;background:linear-gradient(90deg,#059669,#10b981);color:#fff;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px;">
          Ver Meu Pedido →
        </a>
      </div>
    """
    return _base_template(content, f"Pagamento Confirmado - {raffle_title}")


def build_cancellation_email(
    raffle_title: str,
    buyer_name: str,
    numbers: list[int],
) -> str:
    nums_str = ", ".join(map(str, sorted(numbers)))
    content = f"""
      <h2 style="margin:0 0 8px;color:#f87171;font-size:22px;">⚠️ Reserva Cancelada</h2>
      <p style="color:#9aa4b2;margin:0 0 24px;">
        Olá, <strong style="color:#e6eef6;">{buyer_name}</strong>.
        Sua reserva no sorteio <strong style="color:#a78bfa;">{raffle_title}</strong> foi cancelada por falta de pagamento.
      </p>
      <div style="background:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.2);border-radius:10px;padding:20px;margin-bottom:24px;">
        <p style="margin:0;color:#9aa4b2;">Números liberados: <strong style="color:#f87171;">{nums_str}</strong></p>
      </div>
      <p style="color:#9aa4b2;">Os números foram liberados e podem ser comprados por outros participantes. Se ainda tiver interesse, acesse o sorteio e faça uma nova reserva.</p>
    """
    return _base_template(content, f"Reserva Cancelada - {raffle_title}")


def build_admin_new_order_email(
    raffle_title: str,
    buyer_name: str,
    buyer_whatsapp: str,
    numbers: list[int],
    total_amount: float,
    order_token: str,
    admin_url: str,
) -> str:
    nums_str = ", ".join(map(str, sorted(numbers)))
    content = f"""
      <h2 style="margin:0 0 8px;color:#a78bfa;font-size:22px;">🆕 Nova Reserva!</h2>
      <p style="color:#9aa4b2;margin:0 0 24px;">Uma nova reserva foi feita no sorteio <strong style="color:#a78bfa;">{raffle_title}</strong>.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#9aa4b2;">Comprador:</td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#e6eef6;font-weight:600;">{buyer_name}</td></tr>
        <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#9aa4b2;">WhatsApp:</td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#e6eef6;">{buyer_whatsapp}</td></tr>
        <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#9aa4b2;">Números:</td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#a78bfa;">{nums_str}</td></tr>
        <tr><td style="padding:8px 0;color:#9aa4b2;">Total:</td>
            <td style="padding:8px 0;color:#34d399;font-weight:700;font-size:18px;">R$ {total_amount:.2f}</td></tr>
      </table>
      <div style="text-align:center;">
        <a href="{admin_url}" style="display:inline-block;background:linear-gradient(90deg,#7c3aed,#06b6d4);color:#fff;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px;">
          Ver no Painel Admin →
        </a>
      </div>
    """
    return _base_template(content, f"Nova Reserva - {raffle_title}")
