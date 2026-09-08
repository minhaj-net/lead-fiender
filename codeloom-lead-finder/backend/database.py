"""
backend/database.py
────────────────────
MySQL connection pool and table initializer.
Uses mysql-connector-python (no ORM — keeps things simple and explicit).

Usage:
    from backend.database import get_connection, init_db
"""
import mysql.connector
from mysql.connector import pooling, Error as MySQLError

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Connection pool ────────────────────────────────────────────────────────────

_pool: pooling.MySQLConnectionPool | None = None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="codeloom_pool",
            pool_size=5,
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=False,
        )
        logger.info("MySQL connection pool created.")
    return _pool


def get_connection():
    """Return a pooled MySQL connection. Caller must close() it when done."""
    try:
        return _get_pool().get_connection()
    except MySQLError as exc:
        logger.error("Failed to get DB connection: %s", exc)
        raise


# ── Schema initializer ────────────────────────────────────────────────────────

_CREATE_LEADS_TABLE = """
CREATE TABLE IF NOT EXISTS leads (
    id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    business_name    VARCHAR(255),
    category         VARCHAR(120),
    facebook_url     VARCHAR(512),
    page_url         VARCHAR(512),
    country          VARCHAR(80),
    city             VARCHAR(120),
    website          VARCHAR(512),
    website_status   ENUM('YES','NO','UNCERTAIN') NOT NULL DEFAULT 'UNCERTAIN',
    business_phone   VARCHAR(32),
    business_whatsapp VARCHAR(32),
    source           VARCHAR(255),
    source_post      TEXT,
    lead_score       TINYINT UNSIGNED DEFAULT 0,
    lead_priority    ENUM('HOT','GOOD','MEDIUM','LOW') DEFAULT 'LOW',
    status           ENUM('QUALIFIED','SKIPPED','DUPLICATE','UNCERTAIN','FAILED')
                     NOT NULL DEFAULT 'QUALIFIED',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                     ON UPDATE CURRENT_TIMESTAMP,
    -- Duplicate detection keys
    UNIQUE KEY uq_facebook_url (facebook_url(191)),
    INDEX idx_website_status (website_status),
    INDEX idx_lead_priority  (lead_priority),
    INDEX idx_status         (status),
    INDEX idx_created_at     (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS sources (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    url         VARCHAR(512),
    source_type VARCHAR(80)  DEFAULT 'facebook_group',
    active      TINYINT(1)   DEFAULT 1,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_AUTOMATION_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS automation_runs (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    started_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stopped_at  DATETIME,
    status      ENUM('RUNNING','STOPPED','COMPLETED','FAILED') DEFAULT 'RUNNING',
    leads_found INT UNSIGNED DEFAULT 0,
    leads_saved INT UNSIGNED DEFAULT 0,
    error_msg   TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def init_db() -> None:
    """
    Create all required tables if they don't already exist.
    Called once on backend startup.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for ddl in [
            _CREATE_LEADS_TABLE,
            _CREATE_SOURCES_TABLE,
            _CREATE_AUTOMATION_RUNS_TABLE,
        ]:
            cursor.execute(ddl)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Database tables verified / created.")
    except MySQLError as exc:
        logger.error("init_db failed: %s", exc)
        raise
