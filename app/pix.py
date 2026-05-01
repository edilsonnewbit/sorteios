"""Gerador de payload BR Code (PIX) simples seguindo formato EMV.

Gera payload com campos básicos: GUI, chave, txid, valor, descricao, merchant name/city
e calcula CRC16 conforme especificação (polinômio 0x1021, init 0xFFFF).
"""
from typing import Optional

def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    poly = 0x1021
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) & 0xFFFF) ^ poly
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF

def _tlv(id_: str, value: str) -> str:
    length = f"{len(value):02d}"
    return f"{id_}{length}{value}"

def generate_pix_payload(key: str, amount: float, description: Optional[str] = None, txid: Optional[str] = None, merchant_name: str = "SORTEIOS", merchant_city: str = "SAO PAULO") -> str:
    """Retorna o payload BR Code (string) pronto para gerar QR code.

    - key: chave PIX (email, cpf, telefone ou EVP)
    - amount: valor em reais
    - description: texto descritivo opcional
    - txid: id da transação (máx 25). Se None, usa "*"
    - merchant_name, merchant_city: nomes para o QR
    """
    if not txid:
        txid = "*"

    # Merchant Account Information (ID 26) -> contains GUI (00) + key (01)
    gui = _tlv("00", "br.gov.bcb.pix")
    chave = _tlv("01", key)
    mai = gui + chave
    if description:
        # some implementations put description in subfield 02 but it's optional
        mai += _tlv("02", description[:99])
    mai_tlv = _tlv("26", mai)

    payload = ""
    # Payload format indicator
    payload += _tlv("00", "01")
    # Merchant account information
    payload += mai_tlv
    # Merchant category (default 0000 = Unspecified)
    payload += _tlv("52", "0000")
    # Currency (986 = BRL)
    payload += _tlv("53", "986")
    # Transaction amount (optional)
    payload += _tlv("54", f"{amount:.2f}")
    # Country
    payload += _tlv("58", "BR")
    # Merchant name (max 25)
    payload += _tlv("59", merchant_name[:25])
    # Merchant city (max 15)
    payload += _tlv("60", merchant_city[:15])
    # Additional data field template (ID 62) with TXID subfield 05
    add = _tlv("05", txid[:25])
    payload += _tlv("62", add)

    # CRC placeholder
    payload_for_crc = payload + "6304"
    crc = _crc16_ccitt(payload_for_crc.encode("utf-8"))
    crc_hex = f"{crc:04X}"
    payload += _tlv("63", crc_hex)
    return payload
