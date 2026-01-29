from __future__ import annotations

from flask import current_app
from sqlalchemy import text
from .. import db
import requests
import json
from datetime import date, datetime
from webapp.dashboard.utils_dashboard import municipios_finder
from ..models import Variedad


def recintos_geojson(bbox_str: str | None) -> dict:
    """
    Devuelve un FeatureCollection GeoJSON con los recintos obtenidos desde
    GeoServer (WFS), filtrados por un bounding box en WGS84.
    """
    if not bbox_str:
        return {"type": "FeatureCollection", "features": []}

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        raise ValueError(f"Formato de bbox no válido: {bbox_str!r}")

    cfg = current_app.config
    wfs_url = cfg.get("GEOSERVER_WFS_URL", "http://100.102.237.86:8080/geoserver/wfs")
    type_name = cfg.get("GEOSERVER_RECINTOS_TYPENAME", "gis_project:recintos_con_propietario")
    gs_user = cfg.get("GEOSERVER_USER")
    gs_password = cfg.get("GEOSERVER_PASSWORD")

    auth = None
    if gs_user and gs_password:
        auth = (gs_user, gs_password)

    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
    }

    try:
        resp = requests.get(wfs_url, params=params, auth=auth, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Error al consultar GeoServer WFS: {exc}") from exc

    data = resp.json()

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise RuntimeError("Respuesta de GeoServer no es un FeatureCollection válido")

    # Enriquecer con nombres de provincia y municipio
    if data.get("features"):
        for feature in data["features"]:
            props = feature.get("properties", {})
            if props.get("provincia"):
                props["nombre_provincia"] = municipios_finder.obtener_nombre_provincia(props["provincia"])
            if props.get("provincia") and props.get("municipio"):
                props["nombre_municipio"] = municipios_finder.obtener_nombre_municipio(
                    props["provincia"], props["municipio"]
                )

    return data

def mis_recintos_geojson(bbox: str | None, user_id: int):
    """
    Devuelve GeoJSON de public.recintos del usuario (id_propietario=user_id),
    filtrado por bbox si viene.
    """
    if not bbox:
        raise ValueError("bbox requerido")

    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox debe tener 4 valores: minx,miny,maxx,maxy")

    minx, miny, maxx, maxy = map(float, parts)

    sql = text("""
        SELECT
            r.id_recinto,
            r.provincia, r.municipio, r.agregado, r.zona,
            r.poligono, r.parcela, r.recinto,
            COALESCE(u.username, 'N/A') AS propietario,
            ST_AsGeoJSON(r.geom)::json AS geom_json
        FROM public.recintos r
        LEFT JOIN public.usuarios u ON u.id_usuario = r.id_propietario
        WHERE r.id_propietario = :uid
          AND ST_Intersects(
                r.geom,
                ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          )
    """)

    rows = db.session.execute(sql, {
        "uid": user_id,
        "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy
    }).mappings().all()

    


    features = []
    for r in rows:
        nombre_provincia = municipios_finder.obtener_nombre_provincia(r["provincia"])
        nombre_municipio = municipios_finder.obtener_nombre_municipio(r["provincia"], r["municipio"])

        features.append({
            "type": "Feature",
            "geometry": r["geom_json"],
            "properties": {
                "id_recinto": r["id_recinto"],
                "provincia": r["provincia"],
                "municipio": r["municipio"],
                "nombre_provincia": nombre_provincia,
                "nombre_municipio": nombre_municipio,
                "agregado": r["agregado"],
                "zona": r["zona"],
                "poligono": r["poligono"],
                "parcela": r["parcela"],
                "recinto": r["recinto"],
                "propietario": r["propietario"],
            },
        })



    
    return {"type": "FeatureCollection", "features": features}

def mis_recinto_detalle(id_recinto: int, user_id: int) -> dict:
    """
    Devuelve los datos completos de UN recinto del usuario, con geojson.
    """
    sql = text("""
        SELECT
            r.id_recinto,
            r.nombre,
            r.superficie_ha,
            r.fecha_creacion,
            r.activa,
            r.provincia, r.municipio, r.agregado, r.zona,
            r.poligono, r.parcela, r.recinto,
            COALESCE(u.username, 'N/A') AS propietario,
            ST_AsGeoJSON(r.geom)::json AS geom_json,
            ST_Y(ST_Centroid(r.geom)) AS centroid_lat,
            ST_X(ST_Centroid(r.geom)) AS centroid_lng
        FROM public.recintos r
        LEFT JOIN public.usuarios u ON u.id_usuario = r.id_propietario
        WHERE r.id_recinto = :rid
          AND r.id_propietario = :uid
        LIMIT 1
    """)

    row = db.session.execute(sql, {"rid": id_recinto, "uid": user_id}).mappings().first()
    if not row:
        return None

    nombre_provincia = municipios_finder.obtener_nombre_provincia(row["provincia"])
    nombre_municipio = municipios_finder.obtener_nombre_municipio(row["provincia"], row["municipio"])
    return {
        "id": row["id_recinto"],
        "provincia": row["provincia"],
        "municipio": row["municipio"],
        "agregado": row["agregado"],
        "zona": row["zona"],
        "nombre_provincia": nombre_provincia,
        "nombre_municipio": nombre_municipio,
        "poligono": row["poligono"],
        "parcela": row["parcela"],
        "recinto": row["recinto"],
        "nombre": row["nombre"],
        "superficie_ha": float(row["superficie_ha"]) if row["superficie_ha"] is not None else None,
        "fecha_creacion": row["fecha_creacion"].isoformat() if row["fecha_creacion"] else None,
        "activa": bool(row["activa"]) if row["activa"] is not None else True,
        "propietario": row["propietario"],
        "geojson": json.dumps(row["geom_json"]),
        "centroid_lat": float(row["centroid_lat"]) if row["centroid_lat"] is not None else None,
        "centroid_lng": float(row["centroid_lng"]) if row["centroid_lng"] is not None else None
    }

# ---------------------------
# Catálogos
# ---------------------------

def catalogo_usos_sigpac() -> list[dict]:
    sql = text("""
        SELECT codigo, descripcion, grupo
        FROM public.usos_sigpac
        ORDER BY grupo, codigo
    """)
    rows = db.session.execute(sql).mappings().all()
    return [{"codigo": r["codigo"], "descripcion": r["descripcion"], "grupo": r["grupo"]} for r in rows]


def catalogo_productos_fega() -> list[dict]:
    sql = text("""
        SELECT codigo, descripcion
        FROM public.productos_fega
        ORDER BY codigo
    """)
    rows = db.session.execute(sql).mappings().all()
    return [{"codigo": int(r["codigo"]), "descripcion": r["descripcion"]} for r in rows]

# ---------------------------
# Catálogos Operaciones (SIEX)
# ---------------------------

def catalogo_operaciones_list(
    catalogo: str,
    parent: str | None = None,
    q: str | None = None,
    limit: int = 200
) -> list[dict]:
    """
    Lista elementos del catálogo (para selects y typeahead).
    - catalogo: nombre del catálogo (ej: RIEGO_SISTEMA, FERT_PRODUCTO)
    - parent: filtra por codigo_padre (jerárquicos)
    - q: búsqueda parcial por nombre (typeahead)
    - limit: límite de resultados
    """
    sql = text("""
        SELECT catalogo, codigo, codigo_padre, nombre, descripcion
        FROM public.catalogos_operaciones
        WHERE catalogo = :cat
          AND (fecha_baja IS NULL OR fecha_baja > CURRENT_DATE)
          AND (:parent IS NULL OR codigo_padre = :parent)
          AND (:q IS NULL OR nombre ILIKE :qpat)
        ORDER BY
          CASE WHEN codigo ~ '^[0-9]+$' THEN codigo::int ELSE 999999 END,
          nombre
        LIMIT :lim
    """)

    rows = db.session.execute(sql, {
        "cat": (catalogo or "").upper().strip(),
        "parent": parent,
        "q": q,
        "qpat": f"%{q}%" if q else None,
        "lim": int(limit) if limit else 200
    }).mappings().all()

    return [dict(r) for r in rows]


def catalogo_operaciones_item(
    catalogo: str,
    codigo: str,
    parent: str | None = None
) -> dict | None:
    """
    Devuelve un elemento del catálogo con extra (para autocompletar datos).
    """
    sql = text("""
        SELECT catalogo, codigo, codigo_padre, nombre, descripcion, extra
        FROM public.catalogos_operaciones
        WHERE catalogo = :cat
          AND codigo = :cod
          AND (:parent IS NULL OR codigo_padre = :parent)
        LIMIT 1
    """)
    row = db.session.execute(sql, {
        "cat": (catalogo or "").upper().strip(),
        "cod": str(codigo).strip(),
        "parent": parent
    }).mappings().first()

    return dict(row) if row else None

# ---------------------------
# Helpers sistema_cultivo
# ---------------------------
def _extract_sistema_cultivo_codigo(data: dict) -> str | None:
    """
    Acepta:
      - data["sistema_cultivo"] = {codigo, label, fuente}
      - data["sistema_cultivo_codigo"] = "X"
    Devuelve el codigo (str) o None.
    """
    if not data:
        return None

    sc = data.get("sistema_cultivo")
    if isinstance(sc, dict):
        cod = sc.get("codigo")
        cod = (str(cod).strip() if cod is not None else None)
        return cod or None

    cod = data.get("sistema_cultivo_codigo")
    cod = (str(cod).strip() if cod is not None else None)
    return cod or None


def _normalize_avanzado(av) -> dict | None:
    """
    Normaliza avanzado para guardar:
      - si viene vacío -> None
      - si viene dict con todo null -> None
    """
    if not av or not isinstance(av, dict):
        return None

    # recoge "hojas" que suelen ser {codigo,label,...} o null
    def is_filled(x):
        if not x:
            return False
        if isinstance(x, dict):
            # si tiene codigo o label con algo
            cod = str(x.get("codigo") or "").strip()
            lab = str(x.get("label") or "").strip()
            return bool(cod or lab)
        return bool(str(x).strip())

    vals = []
    for k, v in av.items():
        if k == "material_vegetal" and isinstance(v, dict):
            vals.append(v.get("tipo"))
            vals.append(v.get("detalle"))
        else:
            vals.append(v)

    return av if any(is_filled(v) for v in vals) else None


def _sistema_cultivo_obj(codigo: str | None) -> dict | None:
    """
    Construye el objeto {codigo,label,fuente:"SIEX"} a partir del catálogo SISTEMA_CULTIVO.
    Si no hay codigo -> None
    """
    if not codigo:
        return None
    item = catalogo_operaciones_item("SISTEMA_CULTIVO", codigo)
    label = None
    if item:
        label = (item.get("nombre") or item.get("descripcion") or "").strip() or None
    return {
        "codigo": str(codigo).strip(),
        "label": label or str(codigo).strip(),
        "fuente": "SIEX",
    }

# ---------------------------
# Cultivos
# ---------------------------

def get_cultivo_recinto(recinto_id: int) -> dict | None:
    # Devuelve el cultivo del recinto si existe.
    sql = text("""
        SELECT
        c.id_cultivo, c.id_recinto, c.tipo_cultivo, c.variedad,
        c.fecha_siembra, c.fecha_implantacion,
        c.fecha_cosecha_estimada, c.fecha_cosecha_real,
        c.estado, c.uso_sigpac, c.sistema_explotacion, c.tipo_registro, c.campana,
        c.id_padre, c.cod_producto, c.cultivo_custom, c.origen_cultivo,
        c.cosecha_estimada_auto, c.observaciones,
        c.sistema_cultivo_codigo, c.avanzado
        FROM public.cultivos c
        WHERE c.id_recinto = :rid
        AND c.id_padre IS NOT NULL
        AND COALESCE(c.estado,'') <> 'eliminado'
        ORDER BY COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC, c.id_cultivo DESC
        LIMIT 1
    """)

    row = db.session.execute(sql, {"rid": recinto_id}).mappings().first()
    if not row:
        return None

    def _d(x):
        return x.isoformat() if x else None

    return {
        "id_cultivo": row["id_cultivo"],
        "id_recinto": row["id_recinto"],
        "tipo_cultivo": row["tipo_cultivo"],
        "variedad": row["variedad"],
        "fecha_siembra": _d(row["fecha_siembra"]),
        "fecha_implantacion": _d(row["fecha_implantacion"]),
        "fecha_cosecha_estimada": _d(row["fecha_cosecha_estimada"]),
        "fecha_cosecha_real": _d(row["fecha_cosecha_real"]),
        "estado": row["estado"],
        "uso_sigpac": row["uso_sigpac"],
        "sistema_explotacion": row["sistema_explotacion"],
        "tipo_registro": row["tipo_registro"],
        "campana": row["campana"],
        "id_padre": row["id_padre"],
        "cod_producto": row["cod_producto"],
        "cultivo_custom": row["cultivo_custom"],
        "origen_cultivo": row["origen_cultivo"],
        "cosecha_estimada_auto": bool(row["cosecha_estimada_auto"]) if row["cosecha_estimada_auto"] is not None else False,
        "observaciones": row["observaciones"],
        "sistema_cultivo_codigo": row["sistema_cultivo_codigo"],
        "sistema_cultivo": _sistema_cultivo_obj(row["sistema_cultivo_codigo"]),
        "avanzado": row["avanzado"],
    }

def normalize_cultivo_payload(data: dict, existing: dict | None = None) -> dict:
    """
    Normaliza el payload para evitar errores típicos:
    - Si tipo_registro=CAMPANA: asegura fecha_siembra y fecha_implantacion (al menos una y las duplica).
    - Si tipo_registro=IMPLANTACION: asegura fecha_implantacion (y opcionalmente duplica a fecha_siembra).
    - Si campana es None en CAMPANA: la calcula como año de fecha inicio.
    """
    d = dict(data or {})

    # tipo_registro final
    tr = (d.get("tipo_registro") or (existing.get("tipo_registro") if existing else "") or "").upper().strip()
    if not tr:
        tr = "CAMPANA"  # default razonable

    # fechas nuevas o existentes
    fecha_siembra = d.get("fecha_siembra") or (existing.get("fecha_siembra") if existing else None)
    fecha_implantacion = d.get("fecha_implantacion") or (existing.get("fecha_implantacion") if existing else None)

    # Normalización
    if tr == "CAMPANA":
        # Si sólo llega una, copia a la otra
        if fecha_siembra and not fecha_implantacion:
            d["fecha_implantacion"] = fecha_siembra
            fecha_implantacion = fecha_siembra
        elif fecha_implantacion and not fecha_siembra:
            d["fecha_siembra"] = fecha_implantacion
            fecha_siembra = fecha_implantacion

        # Campaña: si viene vacía, usa el año de la fecha de inicio
        if d.get("campana") in (None, "", 0):
            base = fecha_siembra or fecha_implantacion
            if base and isinstance(base, str) and len(base) >= 4 and base[:4].isdigit():
                d["campana"] = int(base[:4])

    elif tr == "IMPLANTACION":
        # Para implantación, asegura fecha_implantacion si sólo llega siembra
        if fecha_siembra and not fecha_implantacion:
            d["fecha_implantacion"] = fecha_siembra
            fecha_implantacion = fecha_siembra

        # Garantizar que siempre exista fecha_siembra también:
        if fecha_implantacion and not d.get("fecha_siembra"):
            d["fecha_siembra"] = fecha_implantacion

    # Devuelve payload ya corregido
    d["tipo_registro"] = tr
    return d

def create_cultivo_recinto(recinto_id: int, data: dict) -> dict:
    """
    Crea el único cultivo del recinto. Si ya existe, error.
    También crea la variedad si es nueva.
    """
    existing = get_cultivo_recinto(recinto_id)

    # Normaliza antes de insertar
    data = normalize_cultivo_payload(data)

    # ============================================
    # Crear variedad si es nueva
    # ============================================
    variedad_nombre = data.get("variedad", "").strip() if data.get("variedad") else None
    cod_producto = data.get("cod_producto")
    avanzado_normalizado = _normalize_avanzado(data.get("avanzado")) or {}
    
    if variedad_nombre:
        # Buscar si la variedad ya existe (case insensitive)
        variedad_existente = Variedad.query.filter(
            db.func.lower(Variedad.nombre) == variedad_nombre.lower()
        ).first()
        
        if not variedad_existente:
            # No existe, crear nueva variedad
            nueva_variedad = Variedad(
                nombre=variedad_nombre,
                producto_fega_id=cod_producto if cod_producto else None
            )
            db.session.add(nueva_variedad)
            db.session.flush()  # Flush para que esté disponible pero sin commit aún
            
            print(f"✓ Nueva variedad creada: {variedad_nombre} (ID: {nueva_variedad.id_variedad})")
        else:
            print(f"✓ Variedad existente encontrada: {variedad_existente.nombre}")
    
    params = {
        "id_recinto": recinto_id,
        "uso_sigpac": data.get("uso_sigpac"),
        "sistema_explotacion": data.get("sistema_explotacion"),
        "tipo_registro": data.get("tipo_registro"),
        "campana": data.get("campana"),
        "id_padre": data.get("id_padre"),
        "cod_producto": data.get("cod_producto"),
        "cultivo_custom": data.get("cultivo_custom"),
        "origen_cultivo": data.get("origen_cultivo"),
        "variedad": variedad_nombre,  # Usar el nombre normalizado
        "estado": data.get("estado", "planificado"),
        "fecha_siembra": data.get("fecha_siembra"),
        "fecha_implantacion": data.get("fecha_implantacion"),
        "fecha_cosecha_estimada": data.get("fecha_cosecha_estimada"),
        "fecha_cosecha_real": data.get("fecha_cosecha_real"),
        "cosecha_estimada_auto": data.get("cosecha_estimada_auto", False),
        "observaciones": data.get("observaciones"),
        "sistema_cultivo_codigo": _extract_sistema_cultivo_codigo(data),
        "avanzado": json.dumps(avanzado_normalizado),
    }

    if existing:
        params["id_padre"] = existing["id_cultivo"]

    sql = text("""
        INSERT INTO public.cultivos (
        id_recinto,
        uso_sigpac,
        sistema_explotacion,
        tipo_registro,
        campana,
        id_padre,
        cod_producto,
        cultivo_custom,
        origen_cultivo,
        variedad,
        estado,
        fecha_siembra,
        fecha_implantacion,
        fecha_cosecha_estimada,
        fecha_cosecha_real,
        cosecha_estimada_auto,
        observaciones,
        sistema_cultivo_codigo,
        avanzado
        )
        VALUES (
        :id_recinto,
        :uso_sigpac,
        :sistema_explotacion,
        :tipo_registro,
        :campana,
        :id_padre,
        :cod_producto,
        :cultivo_custom,
        :origen_cultivo,
        :variedad,
        :estado,
        :fecha_siembra,
        :fecha_implantacion,
        :fecha_cosecha_estimada,
        :fecha_cosecha_real,
        :cosecha_estimada_auto,
        :observaciones,
        :sistema_cultivo_codigo,
        CAST(:avanzado AS jsonb)
        )
        RETURNING id_cultivo
    """)


    new_id = db.session.execute(sql, params).scalar_one()
    # Si no venía con id_padre, lo marcamos como "cadena actual"
    if params.get("id_padre") in (None, "", 0):
        db.session.execute(text("""
            UPDATE public.cultivos
            SET id_padre = id_cultivo
            WHERE id_cultivo = :cid
        """), {"cid": new_id})

    db.session.commit()
    return get_cultivo_recinto(recinto_id)

def create_cultivo_historico_recinto(recinto_id: int, data: dict) -> dict:
    # Normaliza fechas/campaña
    data = normalize_cultivo_payload(data)

    # Fecha inicio nueva
    new_inicio = data.get("fecha_siembra") or data.get("fecha_implantacion")
    if not new_inicio:
        raise ValueError("Selecciona fecha de inicio")

    # Fecha inicio actual (si existe)
    cur = get_cultivo_recinto(recinto_id)
    if cur:
        cur_inicio = cur.get("fecha_siembra") or cur.get("fecha_implantacion")
        # si intentan meter algo igual o más reciente => impedir para no cambiar el actual
        if cur_inicio and str(new_inicio) >= str(cur_inicio):
            raise ValueError("Para añadir al histórico, la fecha de inicio debe ser anterior al cultivo actual.")

    params = {
        "id_recinto": recinto_id,
        "uso_sigpac": data.get("uso_sigpac"),
        "sistema_explotacion": data.get("sistema_explotacion"),
        "tipo_registro": data.get("tipo_registro"),
        "campana": data.get("campana"),
        "id_padre": None,  # histórico “suelto”
        "cod_producto": data.get("cod_producto"),
        "cultivo_custom": data.get("cultivo_custom"),
        "origen_cultivo": data.get("origen_cultivo"),
        "variedad": data.get("variedad"),
        "estado": data.get("estado", "planificado"),
        "fecha_siembra": data.get("fecha_siembra"),
        "fecha_implantacion": data.get("fecha_implantacion"),
        "fecha_cosecha_estimada": data.get("fecha_cosecha_estimada"),
        "fecha_cosecha_real": data.get("fecha_cosecha_real"),
        "cosecha_estimada_auto": data.get("cosecha_estimada_auto", False),
        "observaciones": data.get("observaciones"),
        "sistema_cultivo_codigo": _extract_sistema_cultivo_codigo(data),
        "avanzado": json.dumps(_normalize_avanzado(data.get("avanzado"))),
    }

    sql = text("""
        INSERT INTO public.cultivos (
        id_recinto, uso_sigpac, sistema_explotacion, tipo_registro, campana,
        id_padre, cod_producto, cultivo_custom, origen_cultivo, variedad, estado,
        fecha_siembra, fecha_implantacion, fecha_cosecha_estimada, fecha_cosecha_real,
        cosecha_estimada_auto, sistema_cultivo_codigo, avanzado, observaciones
        )
        VALUES (
        :id_recinto, :uso_sigpac, :sistema_explotacion, :tipo_registro, :campana,
        :id_padre, :cod_producto, :cultivo_custom, :origen_cultivo, :variedad, :estado,
        :fecha_siembra, :fecha_implantacion, :fecha_cosecha_estimada, :fecha_cosecha_real,
        :cosecha_estimada_auto, :sistema_cultivo_codigo, CAST(:avanzado AS jsonb), :observaciones
        )
        RETURNING id_cultivo
    """)

    db.session.execute(sql, params).scalar_one()
    db.session.commit()
    return {"ok": True}


def patch_cultivo_recinto(recinto_id: int, data: dict) -> dict:
    """
    En vez de sobrescribir, crea una NUEVA fila (versión),
    dejando la anterior como histórico.
    También crea la variedad si es nueva.
    """
    prev = get_cultivo_recinto(recinto_id)
    if not prev:
        raise ValueError("no_existe")

    allowed = {
        "uso_sigpac",
        "sistema_explotacion",
        "tipo_registro",
        "campana",
        "cod_producto",
        "cultivo_custom",
        "origen_cultivo",
        "variedad",
        "estado",
        "fecha_siembra",
        "fecha_implantacion",
        "fecha_cosecha_estimada",
        "fecha_cosecha_real",
        "cosecha_estimada_auto",
        "observaciones",
        "tipo_cultivo",
        "sistema_cultivo_codigo",
        "avanzado",
    }

    merged = {k: prev.get(k) for k in allowed}
    for k, v in (data or {}).items():
        if k in allowed:
            merged[k] = v

    merged["id_recinto"] = recinto_id
    merged["id_padre"] = prev["id_cultivo"]

    # normaliza fechas/campaña si hace falta
    merged = normalize_cultivo_payload(merged, existing=prev)

    merged["sistema_cultivo_codigo"] = _extract_sistema_cultivo_codigo(merged)
    merged["avanzado"] = _normalize_avanzado(merged.get("avanzado")) or {}

    # ============================================
    # NUEVA LÓGICA: Crear variedad si es nueva
    # ============================================
    variedad_nombre = merged.get("variedad", "").strip() if merged.get("variedad") else None
    cod_producto = merged.get("cod_producto")
    
    if variedad_nombre:
        try:
            # Buscar si la variedad ya existe (case insensitive)
            variedad_existente = Variedad.query.filter(
                db.func.lower(Variedad.nombre) == variedad_nombre.lower()
            ).first()
            
            if not variedad_existente:
                # No existe, crear nueva variedad
                nueva_variedad = Variedad(
                    nombre=variedad_nombre,
                    producto_fega_id=cod_producto if cod_producto else None
                )
                db.session.add(nueva_variedad)
                db.session.flush()
                
                print(f"✓ Nueva variedad creada al editar: {variedad_nombre} (ID: {nueva_variedad.id_variedad})")
            else:
                print(f"✓ Variedad existente encontrada: {variedad_existente.nombre}")
        except Exception as e:
            print(f"⚠️ Error al crear/buscar variedad: {str(e)}")
    # ============================================

    params = {
        "id_recinto": recinto_id,
        "id_padre": merged.get("id_padre"),
        "uso_sigpac": merged.get("uso_sigpac"),
        "sistema_explotacion": merged.get("sistema_explotacion"),
        "tipo_registro": merged.get("tipo_registro"),
        "campana": merged.get("campana"),
        "cod_producto": merged.get("cod_producto"),
        "cultivo_custom": merged.get("cultivo_custom"),
        "origen_cultivo": merged.get("origen_cultivo"),
        "tipo_cultivo": merged.get("tipo_cultivo"),
        "variedad": variedad_nombre,
        "estado": merged.get("estado", "planificado"),
        "fecha_siembra": merged.get("fecha_siembra"),
        "fecha_implantacion": merged.get("fecha_implantacion"),
        "fecha_cosecha_estimada": merged.get("fecha_cosecha_estimada"),
        "fecha_cosecha_real": merged.get("fecha_cosecha_real"),
        "cosecha_estimada_auto": merged.get("cosecha_estimada_auto", False),
        "observaciones": merged.get("observaciones"),
        "sistema_cultivo_codigo": merged.get("sistema_cultivo_codigo"),
        "avanzado": json.dumps(merged.get("avanzado")),
    }

    sql = text("""
        INSERT INTO public.cultivos (
          id_recinto, id_padre,
          uso_sigpac, sistema_explotacion, tipo_registro, campana,
          cod_producto, cultivo_custom, origen_cultivo, tipo_cultivo,
          variedad, estado,
          fecha_siembra, fecha_implantacion,
          fecha_cosecha_estimada, fecha_cosecha_real,
          cosecha_estimada_auto, observaciones,
          sistema_cultivo_codigo, avanzado
        )
        VALUES (
          :id_recinto, :id_padre,
          :uso_sigpac, :sistema_explotacion, :tipo_registro, :campana,
          :cod_producto, :cultivo_custom, :origen_cultivo, :tipo_cultivo,
          :variedad, :estado,
          :fecha_siembra, :fecha_implantacion,
          :fecha_cosecha_estimada, :fecha_cosecha_real,
          :cosecha_estimada_auto, :observaciones,
          :sistema_cultivo_codigo, CAST(:avanzado AS jsonb)
        )
        RETURNING id_cultivo
    """)

    db.session.execute(sql, params).scalar_one()
    db.session.commit()  # Commit tanto del cultivo como de la variedad
    return get_cultivo_recinto(recinto_id)

def delete_cultivo_recinto(recinto_id: int) -> bool:
    """
    Elimina SOLO el cultivo actual (el último) del recinto.
    """
    cultivo = get_cultivo_recinto(recinto_id)
    if not cultivo:
        return False

    sql = text("""
        DELETE FROM public.cultivos
        WHERE id_recinto = :rid
          AND id_cultivo = :cid
    """)

    res = db.session.execute(sql, {"rid": recinto_id, "cid": cultivo["id_cultivo"]})
    db.session.commit()

    # Tras borrar el actual, convertir cualquier resto de "cadena actual" a histórico
    db.session.execute(text("""
        UPDATE public.cultivos
        SET id_padre = NULL
        WHERE id_recinto = :rid
        AND id_padre IS NOT NULL
    """), {"rid": recinto_id})
    
    db.session.commit()
    return res.rowcount > 0

def _row_to_jsonable(row) -> dict:
    d = dict(row) if row else None
    if not d:
        return None
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d

def get_cultivo_by_id(id_cultivo: int, user_id: int) -> dict | None:
    sql = text("""
        SELECT c.*
        FROM public.cultivos c
        JOIN public.recintos r ON r.id_recinto = c.id_recinto
        WHERE c.id_cultivo = :cid
          AND r.id_propietario = :uid
        LIMIT 1
    """)
    row = db.session.execute(sql, {"cid": id_cultivo, "uid": user_id}).mappings().first()
    return _row_to_jsonable(row)

def delete_cultivo_by_id(id_cultivo: int, user_id: int) -> bool:
    row = get_cultivo_by_id(id_cultivo, user_id)
    if not row:
        return False

    # --- BLOQUEO: no permitir borrar el cultivo actual desde /cultivos/<id> ---
    cur = get_cultivo_recinto(row["id_recinto"])
    if cur and int(cur["id_cultivo"]) == int(id_cultivo):
        raise ValueError("No puedes borrar el cultivo actual desde el histórico. Hazlo desde la página principal del cultivo.")

    sql = text("""
        DELETE FROM public.cultivos c
        USING public.recintos r
        WHERE c.id_cultivo = :cid
          AND r.id_recinto = c.id_recinto
          AND r.id_propietario = :uid
    """)
    res = db.session.execute(sql, {"cid": id_cultivo, "uid": user_id})
    db.session.commit()
    return res.rowcount > 0

def patch_cultivo_by_id(id_cultivo: int, user_id: int, data: dict) -> dict:
    prev = get_cultivo_by_id(id_cultivo, user_id)
    if not prev:
        raise ValueError("no_existe")

    allowed = {
        "uso_sigpac",
        "sistema_explotacion",
        "tipo_registro",
        "campana",
        "cod_producto",
        "cultivo_custom",
        "origen_cultivo",
        "variedad",
        "estado",
        "fecha_siembra",
        "fecha_implantacion",
        "fecha_cosecha_estimada",
        "fecha_cosecha_real",
        "cosecha_estimada_auto",
        "observaciones",
        "tipo_cultivo",
        "sistema_cultivo_codigo",
        "avanzado",
    }

    merged = {k: prev.get(k) for k in allowed}
    for k, v in (data or {}).items():
        if k in allowed:
            merged[k] = v

    # normaliza fechas/campaña si hace falta
    merged = normalize_cultivo_payload(merged, existing=prev)

    merged["sistema_cultivo_codigo"] = _extract_sistema_cultivo_codigo(merged)
    merged["avanzado"] = _normalize_avanzado(merged.get("avanzado"))

    variedad_nombre = merged.get("variedad", "").strip() if merged.get("variedad") else None
    cod_producto = merged.get("cod_producto")
    
    if variedad_nombre:
        try:
            # Buscar si la variedad ya existe (case insensitive)
            variedad_existente = Variedad.query.filter(
                db.func.lower(Variedad.nombre) == variedad_nombre.lower()
            ).first()
            
            if not variedad_existente:
                nueva_variedad = Variedad(
                    nombre=variedad_nombre,
                    producto_fega_id=cod_producto if cod_producto else None
                )
                db.session.add(nueva_variedad)
                db.session.flush()
                
                print(f"✓ Nueva variedad creada al editar (by_id): {variedad_nombre} (ID: {nueva_variedad.id_variedad})")
            else:
                print(f"✓ Variedad existente encontrada: {variedad_existente.nombre}")
        except Exception as e:
            print(f"⚠️ Error al crear/buscar variedad: {str(e)}")
    # ============================================

    params = {"cid": id_cultivo}
    sets = []
    for k in allowed:
        if k in merged:
            if k == "avanzado":
                sets.append(f"{k} = CAST(:{k} AS jsonb)")
                params[k] = json.dumps(merged.get(k))
            else:
                sets.append(f"{k} = :{k}")
                params[k] = merged.get(k)

    sql = text(f"""
        UPDATE public.cultivos
        SET {", ".join(sets)}
        WHERE id_cultivo = :cid
    """)
    db.session.execute(sql, params)
    db.session.commit()  

    return get_cultivo_by_id(id_cultivo, user_id)

# ---------------------------
# Operaciones
# ---------------------------
def _parse_date_iso(v) -> date | None:
    if not v:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v).strip()
    # admite "YYYY-MM-DD" y también "YYYY-MM-DDTHH:MM..."
    return date.fromisoformat(s[:10])


def _get_tipo_operacion_id(codigo: str) -> int:
    cod = (codigo or "").upper().strip()
    if not cod:
        raise ValueError("tipo_requerido")

    tid = db.session.execute(
        text("SELECT id_tipo_operacion FROM public.tipos_operacion WHERE codigo = :c"),
        {"c": cod},
    ).scalar()

    if not tid:
        raise ValueError(f"tipo_no_valido:{cod}")

    return int(tid)


def _assert_recinto_owner(recinto_id: int, user_id: int) -> None:
    ok = db.session.execute(
        text("SELECT 1 FROM public.recintos WHERE id_recinto = :rid AND id_propietario = :uid"),
        {"rid": recinto_id, "uid": user_id},
    ).scalar()
    if not ok:
        raise ValueError("recinto_no_encontrado_o_sin_permiso")


def list_operaciones_recinto(recinto_id: int, user_id: int, limit: int | None = None) -> list[dict]:
    _assert_recinto_owner(recinto_id, user_id)

    if limit is not None and limit <= 0:
        limit = None

    sql = text("""
        SELECT
            o.id_operacion,
            o.id_recinto,
            t.codigo AS tipo,
            o.fecha,
            o.descripcion,
            o.detalle,
            COALESCE(o.meta, '{}'::jsonb) AS meta,
            o.created_at,
            o.updated_at
        FROM public.operaciones o
        JOIN public.tipos_operacion t ON t.id_tipo_operacion = o.id_tipo_operacion
        WHERE o.id_recinto = :rid
        ORDER BY o.fecha DESC, o.id_operacion DESC
        """ + ("" if limit is None else " LIMIT :lim")
    )

    params = {"rid": recinto_id}
    if limit is not None:
        params["lim"] = limit

    rows = db.session.execute(sql, params).mappings().all()

    out = []
    for r in rows:
        d = dict(r)
        # convertir fechas/datetimes a ISO como haces en cultivos
        for k, v in list(d.items()):
            if isinstance(v, (datetime, date)):
                d[k] = v.isoformat()
        out.append(d)

    return out


def create_operacion_recinto(recinto_id: int, user_id: int, payload: dict) -> dict:
    _assert_recinto_owner(recinto_id, user_id)

    tipo = (payload.get("tipo") or "").upper().strip()
    fecha = _parse_date_iso(payload.get("fecha"))
    if not tipo:
        raise ValueError("tipo_requerido")
    if not fecha:
        raise ValueError("fecha_requerida")

    id_tipo = _get_tipo_operacion_id(tipo)

    descripcion = payload.get("descripcion", None)
    detalle = payload.get("detalle") or {}
    meta = {
        "schema_version": payload.get("schema_version", 1),
        # guardamos snapshot completo para histórico y para no depender del catálogo en el futuro
        "payload_snapshot": {
            "tipo": tipo,
            "fecha": str(fecha),
            "descripcion": descripcion,
            "detalle": detalle,
        },
    }

    sql = text("""
        INSERT INTO public.operaciones (
            id_recinto, id_tipo_operacion, fecha, descripcion, detalle, meta
        )
        VALUES (
            :rid, :tid, :fecha, :desc, CAST(:detalle AS jsonb), CAST(:meta AS jsonb)
        )
        RETURNING id_operacion
    """)

    new_id = db.session.execute(sql, {
        "rid": recinto_id,
        "tid": id_tipo,
        "fecha": fecha,
        "desc": descripcion,
        "detalle": json.dumps(detalle),
        "meta": json.dumps(meta),
    }).scalar_one()

    db.session.commit()

    # devolver registro creado (para depurar / futuro)
    row = db.session.execute(text("""
        SELECT
            o.id_operacion, o.id_recinto, t.codigo AS tipo, o.fecha, o.descripcion, o.detalle, o.meta, o.created_at, o.updated_at
        FROM public.operaciones o
        JOIN public.tipos_operacion t ON t.id_tipo_operacion = o.id_tipo_operacion
        WHERE o.id_operacion = :oid
        LIMIT 1
    """), {"oid": new_id}).mappings().first()

    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def patch_operacion_by_id(id_operacion: int, user_id: int, payload: dict) -> dict:
    # comprobar propiedad via join operaciones -> recintos
    ok = db.session.execute(text("""
        SELECT o.id_recinto
        FROM public.operaciones o
        JOIN public.recintos r ON r.id_recinto = o.id_recinto
        WHERE o.id_operacion = :oid
          AND r.id_propietario = :uid
        LIMIT 1
    """), {"oid": id_operacion, "uid": user_id}).scalar()

    if not ok:
        raise ValueError("operacion_no_encontrada_o_sin_permiso")

    tipo = (payload.get("tipo") or "").upper().strip()
    fecha = _parse_date_iso(payload.get("fecha"))
    if not tipo:
        raise ValueError("tipo_requerido")
    if not fecha:
        raise ValueError("fecha_requerida")

    id_tipo = _get_tipo_operacion_id(tipo)
    descripcion = payload.get("descripcion", None)
    detalle = payload.get("detalle") or {}

    meta = {
        "schema_version": payload.get("schema_version", 1),
        "payload_snapshot": {
            "tipo": tipo,
            "fecha": str(fecha),
            "descripcion": descripcion,
            "detalle": detalle,
        },
    }

    db.session.execute(text("""
        UPDATE public.operaciones
        SET
            id_tipo_operacion = :tid,
            fecha = :fecha,
            descripcion = :desc,
            detalle = CAST(:detalle AS jsonb),
            meta = CAST(:meta AS jsonb),
            updated_at = now()
        WHERE id_operacion = :oid
    """), {
        "tid": id_tipo,
        "fecha": fecha,
        "desc": descripcion,
        "detalle": json.dumps(detalle),
        "meta": json.dumps(meta),
        "oid": id_operacion,
    })

    db.session.commit()

    row = db.session.execute(text("""
        SELECT
            o.id_operacion, o.id_recinto, t.codigo AS tipo, o.fecha, o.descripcion, o.detalle, o.meta, o.created_at, o.updated_at
        FROM public.operaciones o
        JOIN public.tipos_operacion t ON t.id_tipo_operacion = o.id_tipo_operacion
        WHERE o.id_operacion = :oid
        LIMIT 1
    """), {"oid": id_operacion}).mappings().first()

    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def delete_operacion_by_id(id_operacion: int, user_id: int) -> bool:
    res = db.session.execute(text("""
        DELETE FROM public.operaciones o
        USING public.recintos r
        WHERE o.id_operacion = :oid
          AND r.id_recinto = o.id_recinto
          AND r.id_propietario = :uid
    """), {"oid": id_operacion, "uid": user_id})

    db.session.commit()
    return res.rowcount > 0