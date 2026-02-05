import os
import json
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from dotenv import load_dotenv
load_dotenv()  # carga .env del directorio actual (o cercano)

DATABASE_URL = os.environ.get("DATABASE_URL")  # ej: postgresql://user:pass@host:5432/dbname
FUENTE = os.environ.get("CATALOGOS_FUENTE", "SIEX_CIRCULAR_PAC_4_2025")
BASE_DIR = os.environ.get("CATALOGOS_DIR", ".")  # carpeta donde están los xlsx

# ==========================================================
# Ficheros (puedes renombrarlos, pero entonces actualiza aquí)
# ==========================================================
FILES = {
    # --- Catálogos “agronómicos”
    "ACTIVIDAD_AGRARIA": "Actividad agraria.xlsx",
    "ACTIVIDAD_CUBIERTA": "Actividad sobre la cubierta.xlsx",
    "APROVECHAMIENTO": "Aprovechamiento.xlsx",
    "TIPO_COBERTURA_SUELO": "Tipo de cobertura del suelo.xlsx",
    "DESTINO_CULTIVO": "Destino del cultivo.xlsx",
    "MATERIAL_VEGETAL": "Material vegetal de reproducción.xlsx",

    # --- Riego
    "RIEGO_SISTEMA": "Sistema de riego.xlsx",
    "RIEGO_PROCEDENCIA": "Procedencia del agua de riego.xlsx",

    # --- Fertilización
    "FERT_TIPO": "Tipo de fertilización.xlsx",
    "FERT_METODO": "Método de aplicación de fertilizante.xlsx",
    "FERT_MATERIAL": "Material fertilizante.xlsx",
    "FERT_TRAT_ESTIERCOL": "Tratamiento de estiércoles.xlsx",

    # --- Nutrientes / metales
    "FERT_MACRO": "Macronutrientes.xlsx",
    "FERT_MICRO": "Micronutrientes.xlsx",
    "FERT_METALES": "Metales pesados.xlsx",

    # --- Catálogo potente para typeahead / autocompletar nutrientes
    "FERT_DETALLE_MATERIAL": "Detalle material fertilizante.xlsx",
}

FILES.update({
    # --- Cultivos (avanzado) / labores / material vegetal
    "TIPO_LABOR": "Tipo de labor.xlsx",
    "MVR_PROCEDENCIA": "Procedencia del material vegetal.xlsx",
    "SENP": "Superficies y elementos no productivos (SENP).xlsx",

    # --- Cultivos (NORMAL obligatorio)
    "SISTEMA_CULTIVO": "Sistema de cultivo.xlsx",
})

FILES.update({
    # --- Fitosanitarios (SIEX)
    "FITOS_TIPO_MEDIDA": "Tipo de medida fitosanitaria.xlsx",
    "FITOS_TIPO_PRODUCTO": "Tipo de producto fitosanitario.xlsx",
    "FITOS_ESTADO_FENO": "Estado fenológico.xlsx",
    "FITOS_MALAS_HIERBAS": "Malas hierbas.xlsx",
    "FITOS_ENFERMEDADES": "Enfermedades.xlsx",
    "FITOS_PLAGAS": "Artrópodos y gasterópodos.xlsx",
    "FITOS_MEDIDA_PREV": "Medida preventiva _ cultural.xlsx",
    "FITOS_REGULADORES_OTROS": "Reguladores de crecimiento, rodenticidas y otros.xlsx",
    "FITOS_EFICACIA": "Eficacia del tratamiento.xlsx",
    "FITOS_AUT_EXCEP": "Autorizaciones excepcionales del producto fitosanitario.xlsx",
    "FITOS_JUSTIFICACION": "Justificación de la actuación.xlsx",

    # --- Catálogo de productos fitosanitarios (typeahead)
    "FITOS_PRODUCTOS": "Productos-05_02_2026.xlsx",
})

def _json_sanitize(obj):
    """
    Convierte NaN/NaT de pandas a None (null en JSON), recursivo.
    """
    if obj is None:
        return None
    # pandas NA / NaN
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    return obj

def dumps_json(obj) -> str:
    """
    JSON válido para PostgreSQL (sin NaN).
    """
    return json.dumps(_json_sanitize(obj), ensure_ascii=False, allow_nan=False, default=str)

def norm_date(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    d = pd.to_datetime(v, errors="coerce", dayfirst=True)
    return None if pd.isna(d) else d.date()

def read_xlsx(key: str) -> pd.DataFrame:
    path = os.path.join(BASE_DIR, FILES[key])
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe: {path}")
    # Primera hoja por defecto
    return pd.read_excel(path)

def upsert_rows(conn, rows):
    sql = """
    INSERT INTO public.catalogos_operaciones
      (catalogo, codigo, codigo_padre, nombre, descripcion, fecha_baja, fuente, extra)
    VALUES %s
    ON CONFLICT (catalogo, codigo, codigo_padre) DO UPDATE SET
      nombre = EXCLUDED.nombre,
      descripcion = EXCLUDED.descripcion,
      fecha_baja = EXCLUDED.fecha_baja,
      fuente = EXCLUDED.fuente,
      extra = EXCLUDED.extra
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)

def _s(v):
    # convierte a string seguro (evita .strip() sobre float/NaN)
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return ""
    return str(v).strip()

def add_row(rows, seen, catalogo, codigo, codigo_padre, nombre, descripcion, fecha_baja, extra):
    codigo = _s(codigo)
    codigo_padre = _s(codigo_padre) if codigo_padre is not None else ""
    if not codigo:
        return

    key = (catalogo, codigo, codigo_padre)
    if key in seen:
        return
    seen.add(key)

    nombre_s = _s(nombre)

    # descripcion: permite None real, pero si viene NaN/float -> None o str
    if descripcion is None or (isinstance(descripcion, float) and pd.isna(descripcion)) or pd.isna(descripcion):
        desc_s = None
    else:
        desc_s = str(descripcion).strip()

    rows.append((
        catalogo, codigo, codigo_padre,
        nombre_s,
        desc_s,
        fecha_baja,
        FUENTE,
        dumps_json(extra)
    ))

def main():
    if not DATABASE_URL:
        raise SystemExit("Falta DATABASE_URL en variables de entorno")

    rows = []
    seen = set()

    # ==========================================================
    # A) Catálogos agronómicos
    # ==========================================================

    # 1) Actividad agraria
    df = read_xlsx("ACTIVIDAD_AGRARIA")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "ACTIVIDAD_AGRARIA",
            r.get("Código SIEX", ""),
            "",
            r.get("Actividad agraria", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # 2) Actividad sobre la cubierta
    df = read_xlsx("ACTIVIDAD_CUBIERTA")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "ACTIVIDAD_CUBIERTA",
            r.get("Código SIEX", ""),
            "",
            r.get("Actividad sobre la cubierta", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # 3) Aprovechamiento
    df = read_xlsx("APROVECHAMIENTO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "APROVECHAMIENTO",
            r.get("Código SIEX", ""),
            "",
            r.get("Aprovechamiento", ""),
            (None if pd.isna(r.get("Descripción")) else str(r.get("Descripción")).strip()),
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # 4) Tipo cobertura del suelo
    df = read_xlsx("TIPO_COBERTURA_SUELO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "TIPO_COBERTURA_SUELO",
            r.get("Código SIEX", ""),
            "",
            r.get("Tipo de cobertura del suelo", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # 5) Destino del cultivo
    df = read_xlsx("DESTINO_CULTIVO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "DESTINO_CULTIVO",
            r.get("Código SIEX", ""),
            "",
            r.get("Destino del cultivo", ""),
            (None if pd.isna(r.get("Observaciones")) else str(r.get("Observaciones")).strip()),
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # 6) Material vegetal de reproducción (jerárquico)
    df = read_xlsx("MATERIAL_VEGETAL")
    for _, r in df.iterrows():
        tipo_code = r.get("Código del tipo", "")
        tipo_name = r.get("Tipo de material vegetal de reproducción", "")
        det_code = r.get("Código", "")
        det_name = r.get("Detalle del tipo", "")
        fb = norm_date(r.get("Fecha de baja"))

        # (A) catálogo de TIPOS (padres)
        add_row(
            rows, seen,
            "MVR_TIPO",
            tipo_code,
            "",
            tipo_name,
            None,
            fb,
            {"tipo_code": tipo_code, "tipo_name": tipo_name}
        )

        # (B) catálogo de DETALLES (hijos)
        add_row(
            rows, seen,
            "MVR_DETALLE",
            det_code,
            tipo_code,
            det_name,
            None,
            fb,
            r.to_dict()
        )
    
    # ==========================================================
    # A.2) Catálogos para CULTIVOS (normal + avanzado)
    # ==========================================================

    # Sistema de cultivo (NORMAL, obligatorio en formulario)
    df = read_xlsx("SISTEMA_CULTIVO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "SISTEMA_CULTIVO",
            r.get("Código SIEX", ""),
            "",
            r.get("Sistema de cultivo", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Tipo de labor (AVANZADO)
    df = read_xlsx("TIPO_LABOR")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "TIPO_LABOR",
            r.get("Código SIEX", ""),
            "",
            r.get("Descripción", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Procedencia del material vegetal (AVANZADO)
    df = read_xlsx("MVR_PROCEDENCIA")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "MVR_PROCEDENCIA",
            r.get("Código SIEX", ""),
            "",
            r.get("Procedencia del material vegetal", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # SENP - Superficies y elementos no productivos (AVANZADO)
    df = read_xlsx("SENP")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "SENP",
            r.get("Código SIEX", ""),
            "",
            r.get("Tipo", ""),
            (None if pd.isna(r.get("Observaciones")) else str(r.get("Observaciones")).strip()),
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )


    # ==========================================================
    # B) RIEGO (Sistemas + procedencia)
    # ==========================================================

    # Sistema de riego
    df = read_xlsx("RIEGO_SISTEMA")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "RIEGO_SISTEMA",
            r.get("Código SIEX", ""),
            "",
            r.get("Sistema de riego", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Procedencia del agua de riego
    df = read_xlsx("RIEGO_PROCEDENCIA")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "RIEGO_PROCEDENCIA",
            r.get("Código SIEX", ""),
            "",
            r.get("Procedencia del agua de riego", ""),
            (None if pd.isna(r.get("Observaciones")) else str(r.get("Observaciones")).strip()),
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # ==========================================================
    # C) FERTILIZACIÓN (tipo/método/material/estiércoles)
    # ==========================================================

    # Tipo de fertilización
    df = read_xlsx("FERT_TIPO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "FERT_TIPO",
            r.get("Código SIEX", ""),
            "",
            r.get("Tipo de fertilización", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Método de fertilización
    df = read_xlsx("FERT_METODO")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "FERT_METODO",
            r.get("Código SIEX", ""),
            "",
            r.get("Método de fertilización", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Material fertilizante (tipo de material)
    df = read_xlsx("FERT_MATERIAL")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "FERT_MATERIAL",
            r.get("Código SIEX", ""),
            "",
            r.get("Tipo de material", ""),
            (None if pd.isna(r.get("Campos a registrar (información disponible según tipo de producto o material)"))
             else str(r.get("Campos a registrar (información disponible según tipo de producto o material)")).strip()),
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # Tratamiento de estiércoles
    df = read_xlsx("FERT_TRAT_ESTIERCOL")
    for _, r in df.iterrows():
        add_row(
            rows, seen,
            "FERT_TRAT_ESTIERCOL",
            r.get("Código SIEX", ""),
            "",
            r.get("Tratamiento de estiércoles", ""),
            None,
            norm_date(r.get("Fecha de baja")),
            r.to_dict()
        )

    # ==========================================================
    # D) Macronutrientes / Micronutrientes / Metales
    # ==========================================================
    def import_simple_descripcion(cat_key, catalogo_name):
        df_local = read_xlsx(cat_key)
        for _, r in df_local.iterrows():
            add_row(
                rows, seen,
                catalogo_name,
                r.get("Código SIEX", ""),
                "",
                r.get("Descripción", ""),
                None,
                norm_date(r.get("Fecha de baja")),
                r.to_dict()
            )

    import_simple_descripcion("FERT_MACRO", "FERT_MACRO")
    import_simple_descripcion("FERT_MICRO", "FERT_MICRO")
    import_simple_descripcion("FERT_METALES", "FERT_METALES")

    # ==========================================================
    # E) Catálogo potente: Detalle material fertilizante
    #     - catalogo: FERT_PRODUCTO
    #     - codigo: C_FERTILIZANTE
    #     - codigo_padre: Código SIEX (tipo material) => filtrar por familia
    # ==========================================================
    df = read_xlsx("FERT_DETALLE_MATERIAL")
    for _, r in df.iterrows():
        codigo = r.get("C_FERTILIZANTE", "")
        padre = r.get("Código SIEX", "")  # tipo material (código SIEX)
        nombre = r.get("Nombre producto", "") or f"Fertilizante {codigo}"
        desc = None if pd.isna(r.get("Fabricante")) else str(r.get("Fabricante")).strip()

        add_row(
            rows, seen,
            "FERT_PRODUCTO",
            codigo,
            padre,
            nombre,
            desc,
            None,
            r.to_dict()
        )

    # ==========================================================
    # F) FITOSANITARIOS (SIEX)
    # ==========================================================
    
    def import_siex_catalog(cat_key, catalogo_name, col_nombre, col_desc=None, col_padre=None):
        df_local = read_xlsx(cat_key)
        for _, r in df_local.iterrows():
            add_row(
                rows, seen,
                catalogo_name,
                r.get("Código SIEX", ""),
                (r.get(col_padre, "") if col_padre else ""),
                r.get(col_nombre, ""),
                (None if (not col_desc or pd.isna(r.get(col_desc))) else str(r.get(col_desc)).strip()),
                norm_date(r.get("Fecha de baja")),
                r.to_dict()
            )

    import_siex_catalog("FITOS_TIPO_MEDIDA", "FITOS_TIPO_MEDIDA", "Tipo de medida fitosanitaria")
    import_siex_catalog("FITOS_TIPO_PRODUCTO", "FITOS_TIPO_PRODUCTO", "Tipo de producto fitosanitario")
    import_siex_catalog("FITOS_ESTADO_FENO", "FITOS_ESTADO_FENO", "Estado fenológico")

    # Catálogos con categoría
    import_siex_catalog("FITOS_MALAS_HIERBAS", "FITOS_MALAS_HIERBAS", "Nombre científico", col_desc="Observaciones", col_padre="Categoría")
    import_siex_catalog("FITOS_ENFERMEDADES", "FITOS_ENFERMEDADES", "Nombre científico", col_desc="Observaciones", col_padre="Categoría")
    import_siex_catalog("FITOS_PLAGAS", "FITOS_PLAGAS", "Nombre científico", col_desc="Observaciones", col_padre="Categoría")
    import_siex_catalog("FITOS_REGULADORES_OTROS", "FITOS_REGULADORES_OTROS", "Nombre científico / Denominación en inglés", col_desc="Observaciones", col_padre="Categoría")

    import_siex_catalog("FITOS_MEDIDA_PREV", "FITOS_MEDIDA_PREV", "Medida", col_desc="Observaciones")
    import_siex_catalog("FITOS_EFICACIA", "FITOS_EFICACIA", "Eficacia del tratamiento")
    import_siex_catalog("FITOS_AUT_EXCEP", "FITOS_AUT_EXCEP", "Producto comercial", col_desc="Sustancia activa o formulado")
    import_siex_catalog("FITOS_JUSTIFICACION", "FITOS_JUSTIFICACION", "Justificación de la actuación")

    # ==========================================================
    # G) FITOS_PRODUCTOS (typeahead)
    # ==========================================================
    df = read_xlsx("FITOS_PRODUCTOS")

    def _pick_date(row):
        # Prioridad: FechaCaducidad > FechaLimiteVenta
        d1 = norm_date(row.get("FechaCaducidad"))
        if d1:
            return d1
        d2 = norm_date(row.get("FechaLimiteVenta"))
        if d2:
            return d2
        return None

    for _, r in df.iterrows():
        num_reg = r.get("NumRegistro", "")
        nombre = r.get("Nombre", "")
        titular = r.get("Titular", "")
        fabricante = r.get("Fabricante", "")
        formulado = r.get("Formulado", "")
        estado = r.get("Estado", "")
        obs = r.get("Observaciones", "")

        parts = []
        if _s(formulado): parts.append(_s(formulado))
        if _s(titular): parts.append(f"Titular: {_s(titular)}")
        if _s(fabricante): parts.append(f"Fabricante: {_s(fabricante)}")
        if _s(estado): parts.append(f"Estado: {_s(estado)}")
        if _s(obs): parts.append(f"Obs: {_s(obs)}")
        desc = " · ".join(parts) if parts else None

        add_row(
            rows, seen,
            "FITOS_PRODUCTOS",          # catalogo
            num_reg,                  # codigo (NumRegistro)
            "",                       # codigo_padre
            nombre,                   # nombre
            desc,                     # descripcion
            _pick_date(r),            # fecha_baja (caducidad/limite venta si existe)
            r.to_dict()               # extra (TODO: símbolos, seguridad, fechas, trámite...)
        )


    # ==========================================================
    # Ejecutar UPSERT
    # ==========================================================

    # Acepta URLs de SQLAlchemy y las convierte a psycopg2
    dsn = DATABASE_URL
    if dsn and dsn.startswith("postgresql+psycopg2://"):
        dsn = dsn.replace("postgresql+psycopg2://", "postgresql://", 1)

    conn = psycopg2.connect(dsn)
    try:
        upsert_rows(conn, rows)
        conn.commit()
        print(f"OK: importados/actualizados {len(rows)} registros en catalogos_operaciones.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()