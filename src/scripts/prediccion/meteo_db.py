"""Utilidades para URLs de PostgreSQL (BD maestra gisdb y comunidades)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip('"').strip("'")


def normalize_pg_url(url: str | None) -> str | None:
    if not url:
        return None
    u = _clean(url)
    for prefix in ("postgresql+psycopg2://", "postgresql+asyncpg://", "postgres://"):
        if u.startswith(prefix):
            u = "postgresql://" + u.split("://", 1)[1]
            break
    return u


def build_pg_url(
    *,
    host: str | None = None,
    port: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> str | None:
    host = _clean(host) or "127.0.0.1"
    port = _clean(port) or "5432"
    user = _clean(user)
    pwd = _clean(password)
    db = _clean(database)
    if not all([user, pwd, db]):
        return None
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(pwd)}"
        f"@{host}:{port}/{db}"
    )


def build_pg_url_from_env(database: str | None = None) -> str | None:
    db_name = _clean(database) or _clean(os.getenv("POSTGRES_DB"))
    explicit = normalize_pg_url(os.getenv("DATABASE_URL"))
    if explicit and not database:
        return explicit
    return build_pg_url(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=db_name,
    )


def build_master_url_from_env() -> str:
    explicit = normalize_pg_url(os.getenv("REFERENCE_SOURCE_DATABASE_URL"))
    if explicit:
        return explicit
    master_db = _clean(os.getenv("REFERENCE_SOURCE_DB")) or "gisdb"
    url = build_pg_url_from_env(database=master_db)
    if not url:
        raise RuntimeError(
            "No se pudo construir la URL de la BD maestra "
            "(REFERENCE_SOURCE_DATABASE_URL o POSTGRES_* + REFERENCE_SOURCE_DB)"
        )
    return url


def discover_community_envs(root: str | Path) -> list[tuple[str, Path]]:
    base = Path(root)
    if not base.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        env_path = child / ".env"
        if env_path.is_file():
            found.append((child.name, env_path))
    return found
