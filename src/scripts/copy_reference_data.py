#!/usr/bin/env python3
"""
Copia tablas de referencia compartidas desde la BD maestra (gisdb) a la BD de la instancia.
"""
from __future__ import annotations

import io
import os
import sys

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

TABLES: list[tuple[str, list[str], bool]] = [
    # table, pk columns, dedupe on insert (catalogos puede tener filas repetidas en origen)
    ("public.productos_fega", ["codigo"], False),
    ("public.usos_sigpac", ["codigo"], False),
    ("public.tipos_operacion", ["id_tipo_operacion"], False),
    ("public.catalogos_operaciones", ["catalogo", "codigo", "codigo_padre"], True),
    ("public.estaciones", ["id"], False),
    ("public.variedades", ["id_variedad"], False),
    ("public.datos_diarios", ["id"], False),
]

TRUNCATE_ORDER = [
    "public.datos_diarios",
    "public.variedades",
    "public.catalogos_operaciones",
    "public.estaciones",
    "public.tipos_operacion",
    "public.usos_sigpac",
    "public.productos_fega",
]


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
    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
        for table in TRUNCATE_ORDER:
            if not table_exists(conn, table):
                print(f"  [omit] {table} no existe en destino")
                continue
            cur.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
                    sql.Identifier(*table.split("."))
                )
            )
        cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()


def copy_table(src, dst, table: str, pk_cols: list[str], dedupe: bool) -> int:
    schema, name = table.split(".", 1)
    if not table_exists(src, table):
        print(f"  [omit] {table} no existe en origen")
        return 0
    if not table_exists(dst, table):
        print(f"  [omit] {table} no existe en destino")
        return 0

    with src.cursor() as sc:
        buf = io.BytesIO()
        sc.copy_expert(
            sql.SQL("COPY {} TO STDOUT").format(sql.Identifier(schema, name)).as_string(src),
            buf,
        )
        data = buf.getvalue()

    if not data:
        print(f"  - {table}: 0 filas (origen vacio)")
        return 0

    with dst.cursor() as dc:
        if dedupe:
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
            pk_sql = sql.SQL(", ").join(sql.Identifier(c) for c in pk_cols)
            dc.execute(
                sql.SQL(
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
                ).format(target=sql.Identifier(schema, name), pk=pk_sql)
            )
        else:
            dc.copy_expert(
                sql.SQL("COPY {} FROM STDIN").format(sql.Identifier(schema, name)).as_string(dst),
                io.BytesIO(data),
            )

    dst.commit()

    with dst.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, name)))
        n = int(cur.fetchone()[0])
    print(f"  - {table}: {n} filas")
    return n


def main() -> int:
    load_dotenv()
    target_url = os.getenv("DATABASE_URL")
    source_url = os.getenv("REFERENCE_SOURCE_DATABASE_URL")
    if not target_url:
        print("ERROR: DATABASE_URL no definido")
        return 1
    if not source_url:
        print("ERROR: REFERENCE_SOURCE_DATABASE_URL no definido")
        return 1

    print("Copiando datos de referencia desde BD maestra...")
    src = connect(source_url)
    dst = connect(target_url)
    try:
        truncate_tables(dst)
        total = 0
        for table, pk_cols, dedupe in TABLES:
            total += copy_table(src, dst, table, pk_cols, dedupe)
        print(f"OK: datos de referencia listos")
        return 0
    except Exception as exc:
        dst.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    raise SystemExit(main())
