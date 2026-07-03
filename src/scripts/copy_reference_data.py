#!/usr/bin/env python3
"""
Copia tablas de referencia compartidas desde la BD maestra (gisdb) a la BD de la instancia.
Deduplica filas en origen (gisdb puede tener PK repetidas en algunas tablas).
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# table, pk columns
TABLES: list[tuple[str, list[str]]] = [
    ("public.productos_fega", ["codigo"]),
    ("public.usos_sigpac", ["codigo"]),
    ("public.tipos_operacion", ["id_tipo_operacion"]),
    ("public.catalogos_operaciones", ["catalogo", "codigo", "codigo_padre"]),
    ("public.estaciones", ["id"]),
    ("public.variedades", ["id_variedad"]),
    ("public.datos_diarios", ["id"]),
]

TRUNCATE_TABLES = [t[0] for t in TABLES]


def normalize_pg_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg2://", "postgresql+asyncpg://", "postgres://"):
        if u.startswith(prefix):
            u = "postgresql://" + u.split("://", 1)[1]
            break
    return u


def build_url_from_parts() -> str | None:
    host = (os.getenv("POSTGRES_HOST") or "127.0.0.1").strip().strip('"').strip("'")
    port = (os.getenv("POSTGRES_PORT") or "5432").strip().strip('"').strip("'")
    user = (os.getenv("POSTGRES_USER") or "").strip().strip('"').strip("'")
    pwd = (os.getenv("POSTGRES_PASSWORD") or "").strip().strip('"').strip("'")
    db = (os.getenv("POSTGRES_DB") or "").strip().strip('"').strip("'")
    if not all([user, pwd, db]):
        return None
    from urllib.parse import quote_plus

    return f"postgresql://{quote_plus(user)}:{quote_plus(pwd)}@{host}:{port}/{db}"


def get_urls() -> tuple[str, str]:
    target = normalize_pg_url(os.getenv("DATABASE_URL")) or build_url_from_parts()
    source = normalize_pg_url(os.getenv("REFERENCE_SOURCE_DATABASE_URL"))
    if not target:
        raise RuntimeError("DATABASE_URL / POSTGRES_* no definidos en .env de la instancia")
    if not source:
        raise RuntimeError("REFERENCE_SOURCE_DATABASE_URL no definido (lo pasa crear-comunidad.ps1)")
    return source, target


def connect(url: str):
    return psycopg2.connect(url)


def table_exists(conn, table: str) -> bool:
    schema, name = table.split(".", 1)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, name),
        )
        return cur.fetchone() is not None


def truncate_tables(conn) -> None:
    existing = [t for t in TRUNCATE_TABLES if table_exists(conn, t)]
    if not existing:
        return
    parts = sql.SQL(", ").join(sql.Identifier(*tbl.split(".")) for tbl in existing)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(parts))
    conn.commit()
    print(f"  - Tablas vaciadas: {', '.join(existing)}")


def copy_table(src, dst, table: str, pk_cols: list[str]) -> int:
    schema, name = table.split(".", 1)
    if not table_exists(src, table):
        print(f"  [omit] {table} no existe en origen")
        return 0
    if not table_exists(dst, table):
        print(f"  [omit] {table} no existe en destino")
        return 0

    copy_out = sql.SQL("COPY {} TO STDOUT").format(sql.Identifier(schema, name)).as_string(src)

    with src.cursor() as sc:
        buf = io.BytesIO()
        sc.copy_expert(copy_out, buf)
        data = buf.getvalue()

    if not data:
        print(f"  - {table}: 0 filas (origen vacio)")
        return 0

    pk_sql = sql.SQL(", ").join(sql.Identifier(c) for c in pk_cols)

    with dst.cursor() as dc:
        dc.execute(
            sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING ALL) ON COMMIT DROP").format(
                sql.Identifier("tmp_ref_copy"),
                sql.Identifier(schema, name),
            )
        )
        dc.copy_expert(
            sql.SQL("COPY {} FROM STDIN").format(sql.Identifier("tmp_ref_copy")).as_string(dst),
            io.BytesIO(data),
        )

        if table == "public.catalogos_operaciones":
            insert_sql = sql.SQL(
                """
                INSERT INTO {target}
                SELECT DISTINCT ON ({pk}) *
                FROM tmp_ref_copy
                ORDER BY {pk}
                ON CONFLICT ({pk}) DO UPDATE SET
                  nombre = EXCLUDED.nombre,
                  descripcion = EXCLUDED.descripcion,
                  fecha_baja = EXCLUDED.fecha_baja,
                  fuente = EXCLUDED.fuente,
                  extra = EXCLUDED.extra
                """
            )
        else:
            insert_sql = sql.SQL(
                """
                INSERT INTO {target}
                SELECT DISTINCT ON ({pk}) *
                FROM tmp_ref_copy
                ORDER BY {pk}
                ON CONFLICT ({pk}) DO NOTHING
                """
            )

        dc.execute(insert_sql.format(target=sql.Identifier(schema, name), pk=pk_sql))

    dst.commit()

    with dst.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, name)))
        n = int(cur.fetchone()[0])
    print(f"  - {table}: {n} filas")
    return n


def main() -> int:
    try:
        source_url, target_url = get_urls()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Copiando datos de referencia desde BD maestra...")
    print(f"  Origen:  {source_url.split('@')[-1]}")
    print(f"  Destino: {target_url.split('@')[-1]}")

    src = None
    dst = None
    try:
        src = connect(source_url)
        dst = connect(target_url)
        truncate_tables(dst)
        for table, pk_cols in TABLES:
            copy_table(src, dst, table, pk_cols)
        print("OK: datos de referencia listos")
        return 0
    except Exception as exc:
        if dst is not None:
            dst.rollback()
        print(f"ERROR: {exc}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if src is not None:
            src.close()
        if dst is not None:
            dst.close()


if __name__ == "__main__":
    raise SystemExit(main())
