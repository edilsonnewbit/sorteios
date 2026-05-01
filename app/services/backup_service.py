"""Serviço de backup do banco de dados."""
import os
import datetime
import subprocess
import logging

logger = logging.getLogger(__name__)

BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sorteios.db")


def ensure_backup_dir() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def create_backup() -> dict:
    """Cria backup do banco. Retorna {filename, size_bytes, error}."""
    ensure_backup_dir()
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    error = None
    filename = None
    size_bytes = None

    if DATABASE_URL.startswith("sqlite"):
        filename, size_bytes, error = _backup_sqlite(ts)
    elif DATABASE_URL.startswith("postgresql"):
        filename, size_bytes, error = _backup_postgres(ts)
    else:
        error = f"Banco não suportado para backup: {DATABASE_URL[:20]}"

    return {"filename": filename, "size_bytes": size_bytes, "error": error}


def _backup_sqlite(ts: str) -> tuple[str | None, int | None, str | None]:
    try:
        import sqlite3
        # Extrai o path do banco da URL
        db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.exists(db_path):
            return None, None, f"Banco SQLite não encontrado: {db_path}"

        filename = f"backup_{ts}.db"
        filepath = os.path.join(BACKUP_DIR, filename)

        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(filepath)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        size_bytes = os.path.getsize(filepath)
        logger.info("Backup SQLite criado: %s (%s bytes)", filepath, size_bytes)
        return filename, size_bytes, None
    except Exception as e:
        err = str(e)
        logger.error("Erro no backup SQLite: %s", err)
        return None, None, err


def _backup_postgres(ts: str) -> tuple[str | None, int | None, str | None]:
    try:
        filename = f"backup_{ts}.sql.gz"
        filepath = os.path.join(BACKUP_DIR, filename)
        result = subprocess.run(
            ["pg_dump", DATABASE_URL, "--no-password"],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr.decode()[:500]
            return None, None, f"pg_dump falhou: {err}"

        import gzip
        with gzip.open(filepath, "wb") as f:
            f.write(result.stdout)

        size_bytes = os.path.getsize(filepath)
        logger.info("Backup PostgreSQL criado: %s (%s bytes)", filepath, size_bytes)
        return filename, size_bytes, None
    except Exception as e:
        err = str(e)
        logger.error("Erro no backup PostgreSQL: %s", err)
        return None, None, err


def list_backups() -> list[dict]:
    """Lista os arquivos de backup disponíveis."""
    ensure_backup_dir()
    files = []
    for fname in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if fname.startswith("backup_"):
            fpath = os.path.join(BACKUP_DIR, fname)
            size = os.path.getsize(fpath)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            files.append({"filename": fname, "size_bytes": size, "created_at": mtime.isoformat()})
    return files


def get_backup_path(filename: str) -> str | None:
    """Retorna o path completo de um backup se existir e for seguro."""
    if "/" in filename or ".." in filename:
        return None
    fpath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(fpath):
        return None
    return fpath


# ─── Google Drive ─────────────────────────────────────────────────────────────

def gdrive_configured() -> bool:
    """Retorna True se as variáveis de ambiente do Drive estiverem definidas."""
    return bool(os.getenv("GDRIVE_CREDENTIALS_JSON")) and bool(os.getenv("GDRIVE_FOLDER_ID"))


def _gdrive_service():
    """Cria e retorna o serviço autenticado do Google Drive."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    import json

    creds_env = os.getenv("GDRIVE_CREDENTIALS_JSON", "").strip()
    scopes = ["https://www.googleapis.com/auth/drive.file"]

    # Aceita path para arquivo JSON ou o conteúdo JSON diretamente
    if os.path.exists(creds_env):
        creds = service_account.Credentials.from_service_account_file(creds_env, scopes=scopes)
    else:
        info = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_to_gdrive(filename: str) -> dict:
    """Envia um arquivo de backup para a pasta do Google Drive configurada.

    Retorna {"file_id", "web_view_link", "error"}.
    """
    if not gdrive_configured():
        return {"error": "Google Drive não configurado (GDRIVE_CREDENTIALS_JSON / GDRIVE_FOLDER_ID ausentes)"}

    fpath = get_backup_path(filename)
    if not fpath:
        return {"error": f"Arquivo não encontrado: {filename}"}

    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()

    try:
        from googleapiclient.http import MediaFileUpload

        service = _gdrive_service()
        mime = "application/x-sqlite3" if filename.endswith(".db") else "application/gzip"

        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(fpath, mimetype=mime, resumable=True)

        uploaded = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id,webViewLink,name,size")
            .execute()
        )

        logger.info("Backup enviado ao Drive: %s (id=%s)", filename, uploaded.get("id"))
        return {
            "file_id": uploaded.get("id"),
            "web_view_link": uploaded.get("webViewLink"),
            "error": None,
        }
    except Exception as e:
        err = str(e)
        logger.error("Erro ao enviar backup para o Drive: %s", err)
        return {"error": err}


def list_gdrive_backups() -> list[dict]:
    """Lista os backups na pasta do Drive configurada."""
    if not gdrive_configured():
        return []

    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()

    try:
        service = _gdrive_service()
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id,name,size,createdTime,webViewLink)",
                orderBy="createdTime desc",
                pageSize=50,
            )
            .execute()
        )
        return resp.get("files", [])
    except Exception as e:
        logger.error("Erro ao listar backups no Drive: %s", e)
        return []
