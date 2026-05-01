from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import logging

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sorteios.db")

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    if _IS_SQLITE:
        try:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL;"))
                conn.execute(text("PRAGMA synchronous=NORMAL;"))
                conn.execute(text("PRAGMA foreign_keys=ON;"))
                conn.commit()
        except Exception:
            pass


def _get_sqlite_cols(conn, table: str) -> set:
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def _get_pg_cols(conn, table: str) -> set:
    result = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    )
    return {row[0] for row in result}


def _get_cols(conn, table: str) -> set:
    return _get_sqlite_cols(conn, table) if _IS_SQLITE else _get_pg_cols(conn, table)


def _add_col_if_missing(conn, table: str, col: str, definition: str, existing: set):
    if col not in existing:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
            logger.info("Migration: added %s.%s", table, col)
        except Exception as e:
            logger.debug("Migration skip %s.%s: %s", table, col, e)


def _migrate_schema():
    try:
        with engine.connect() as conn:
            # ── campaigns ──────────────────────────────────────────────────
            cols = _get_cols(conn, "campaigns")

            # slug was always in the model — its absence means an old/incompatible DB.
            # Add it as nullable first, then backfill unique values for existing rows.
            if "slug" not in cols:
                logger.warning("Migration: old schema detected (campaigns.slug missing) — backfilling foundational columns")
                try:
                    conn.execute(text("ALTER TABLE campaigns ADD COLUMN slug VARCHAR(16)"))
                    if _IS_SQLITE:
                        conn.execute(text(
                            "UPDATE campaigns SET slug = 'rifa' || CAST(id AS TEXT) WHERE slug IS NULL"
                        ))
                    else:
                        conn.execute(text(
                            "UPDATE campaigns SET slug = 'rifa' || id::TEXT WHERE slug IS NULL"
                        ))
                    cols.add("slug")
                except Exception as e:
                    logger.warning("Migration: could not add slug column: %s", e)

            # Other foundational columns that may be absent in old schemas
            _add_col_if_missing(conn, "campaigns", "goal_amount", "FLOAT NOT NULL DEFAULT 0", cols)
            _add_col_if_missing(conn, "campaigns", "price_per_quota", "FLOAT NOT NULL DEFAULT 1", cols)
            _add_col_if_missing(conn, "campaigns", "pix_key", "VARCHAR(200)", cols)
            _add_col_if_missing(conn, "campaigns", "draw_date", "DATETIME", cols)
            _add_col_if_missing(conn, "campaigns", "winner_quota_id", "INTEGER", cols)

            # Enhanced fields added in v2
            _add_col_if_missing(conn, "campaigns", "status", "VARCHAR(20) NOT NULL DEFAULT 'active'", cols)
            _add_col_if_missing(conn, "campaigns", "description", "TEXT", cols)
            _add_col_if_missing(conn, "campaigns", "prize_image_url", "VARCHAR(500)", cols)
            _add_col_if_missing(conn, "campaigns", "prize_value", "FLOAT", cols)
            _add_col_if_missing(conn, "campaigns", "rules", "TEXT", cols)
            _add_col_if_missing(conn, "campaigns", "max_per_person", "INTEGER DEFAULT 10", cols)
            _add_col_if_missing(conn, "campaigns", "pix_receiver_name", "VARCHAR(25) DEFAULT 'SORTEIOS'", cols)
            _add_col_if_missing(conn, "campaigns", "pix_receiver_city", "VARCHAR(15) DEFAULT 'SAO PAULO'", cols)
            _add_col_if_missing(conn, "campaigns", "reservation_expires_minutes", "INTEGER DEFAULT 30", cols)

            # ── quotas ─────────────────────────────────────────────────────
            cols = _get_cols(conn, "quotas")
            _add_col_if_missing(conn, "quotas", "status", "VARCHAR(20) NOT NULL DEFAULT 'available'", cols)
            _add_col_if_missing(conn, "quotas", "reserved_by", "VARCHAR(200)", cols)
            _add_col_if_missing(conn, "quotas", "reserved_at", "DATETIME", cols)
            _add_col_if_missing(conn, "quotas", "paid", "BOOLEAN NOT NULL DEFAULT 0", cols)

            # ── users ──────────────────────────────────────────────────────
            # users table is created by create_all; only need to add missing cols for upgrades
            try:
                cols = _get_cols(conn, "users")
                _add_col_if_missing(conn, "users", "company_name", "VARCHAR(200)", cols)
                _add_col_if_missing(conn, "users", "phone", "VARCHAR(30)", cols)
                _add_col_if_missing(conn, "users", "max_raffles", "INTEGER DEFAULT 5", cols)
            except Exception:
                pass  # table may not exist yet — create_all handles it

            # ── campaigns: owner_id ────────────────────────────────────────
            cols = _get_cols(conn, "campaigns")
            _add_col_if_missing(conn, "campaigns", "owner_id", "INTEGER REFERENCES users(id)", cols)

            conn.commit()
    except Exception as e:
        logger.warning("Migration error (non-fatal): %s", e)


def seed_admin(email: str, password: str, name: str = "Super Admin"):
    """Creates the initial admin user if no admin exists."""
    from . import models
    from .auth import hash_password
    session = SessionLocal()
    try:
        exists = session.query(models.User).filter(models.User.role == "admin").first()
        if not exists:
            admin = models.User(
                email=email,
                name=name,
                password_hash=hash_password(password),
                role="admin",
                status="approved",
            )
            session.add(admin)
            session.commit()
            import logging
            logging.getLogger(__name__).info("Admin user seeded: %s", email)
    except Exception as e:
        session.rollback()
        import logging
        logging.getLogger(__name__).warning("Could not seed admin: %s", e)
    finally:
        session.close()
