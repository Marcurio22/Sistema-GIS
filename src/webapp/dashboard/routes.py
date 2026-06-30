from datetime import date, timedelta, datetime
import unicodedata
import re as _re
from  pathlib import Path
from sqlalchemy import text
from .. import db
from flask import jsonify, render_template, current_app, send_file, url_for, request
from flask_login import login_required, current_user
from collections import defaultdict
from ..api.services import visor_start_view_usuario, superficie_geom_por_recinto
from . import dashboard_bp
import json
import logging
import io
import tempfile
import zipfile
from .utils_dashboard import leaflet_bounds_from_tif, obtener_datos_aemet, MunicipiosCodigosFinder
from ..models import Recinto, Contador
import os
from ..dashboard.utils_dashboard import municipios_finder


logger = logging.getLogger('app.dashboard')
logger.setLevel(logging.INFO)


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():

    # ---------------------------
    # AEMET (widget)
    # ---------------------------
    municipios_codigos_finder = MunicipiosCodigosFinder()
    url_widget = municipios_codigos_finder.obtener_url_municipio_usuario(current_user.id_usuario)
    codigo_municipio = municipios_codigos_finder.codigo_recintos(current_user.id_usuario)
    weather = obtener_datos_aemet(codigo_municipio) if codigo_municipio else None

    # ---------------------------
    # Vista inicial recomendada (para el minimapa del dashboard)
    # ---------------------------
    start_view = visor_start_view_usuario(current_user.id_usuario) or {
        "municipio_top": None,
        "center": {"lat": 41.95, "lng": -4.20},
        "bbox": None,
        "zoom_sugerido": 11,
    }

    # ---------------------------
    # Minimapa estático (imagen satélite)
    # ---------------------------
    minimap_img_url = None

    bbox = start_view.get("bbox")
    if bbox and len(bbox) == 4:
        minx, miny, maxx, maxy = bbox

        # ESRI World Imagery (estático)
        minimap_img_url = (
            "https://services.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/export"
            f"?bbox={minx},{miny},{maxx},{maxy}"
            "&bboxSR=4326"
            "&imageSR=3857"
            "&size=600,400"
            "&format=png"
            "&f=image"
        )

    # ---------------------------
    # Resumen rápido
    # ---------------------------
    recintos_q = (
        Recinto.query
        .filter(Recinto.id_propietario == current_user.id_usuario)
        .order_by(Recinto.provincia, Recinto.municipio, Recinto.poligono, Recinto.parcela, Recinto.recinto)
    )

    recintos = recintos_q.all()
    recintos_count = len(recintos)

    # Cultivo principal (por hectáreas ocupadas) usando el cultivo “actual” de cada recinto
    cultivo_principal = None
    if recintos_count > 0:
        sql_cultivo = text("""
            WITH myrec AS (
                SELECT id_recinto, superficie_ha
                FROM public.recintos
                WHERE id_propietario = :uid
                  AND (activa IS TRUE OR activa IS NULL)
            ),
            cur AS (
                SELECT DISTINCT ON (c.id_recinto)
                    c.id_recinto,
                    COALESCE(
                        NULLIF(BTRIM(c.tipo_cultivo), ''),
                        NULLIF(BTRIM(c.cultivo_custom), ''),
                        NULLIF(BTRIM(pf.descripcion), ''),
                        NULLIF(BTRIM(c.uso_sigpac), '')
                    ) AS cultivo
                FROM public.cultivos c
                JOIN myrec r ON r.id_recinto = c.id_recinto
                LEFT JOIN public.productos_fega pf ON pf.codigo = c.cod_producto
                WHERE c.id_padre IS NOT NULL
                  AND COALESCE(c.estado, '') <> 'eliminado'
                ORDER BY
                    c.id_recinto,
                    COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC NULLS LAST,
                    c.id_cultivo DESC
            )
            SELECT cur.cultivo, SUM(COALESCE(ST_Area(geography(r.geom)) / 10000.0, 0)) AS ha
            FROM cur
            JOIN public.recintos r ON r.id_recinto = cur.id_recinto
            WHERE r.id_propietario = :uid
            GROUP BY cur.cultivo
            ORDER BY ha DESC NULLS LAST
            LIMIT 1;
        """)

        row = db.session.execute(sql_cultivo, {"uid": current_user.id_usuario}).mappings().first()
        if row and row.get("cultivo"):
            cultivo_principal = str(row["cultivo"]).strip() or None

    # Operaciones “activas” (últimos 30 días) por recinto
    cutoff = date.today() - timedelta(days=30)

    sql_ops = text("""
        SELECT
            o.id_operacion,
            o.id_recinto,
            t.codigo AS tipo,
            o.fecha,
            o.descripcion,
            o.detalle
        FROM public.operaciones o
        JOIN public.tipos_operacion t ON t.id_tipo_operacion = o.id_tipo_operacion
        JOIN public.recintos r ON r.id_recinto = o.id_recinto
        WHERE r.id_propietario = :uid
          AND (r.activa IS TRUE OR r.activa IS NULL)
          AND o.fecha >= :cutoff
        ORDER BY o.fecha DESC, o.id_operacion DESC
    """)

    rows_ops = db.session.execute(sql_ops, {"uid": current_user.id_usuario, "cutoff": cutoff}).mappings().all()

    ops_by_recinto: dict[int, list[dict]] = defaultdict(list)
    for r in rows_ops:
        ops_by_recinto[int(r["id_recinto"])].append(dict(r))

    def _op_tipo_label(tipo: str | None) -> str:
        t = (tipo or "").upper().strip()
        if t == "RIEGO":
            return "Riego"
        if t == "FERTILIZACION":
            return "Fertilización"
        if t == "FITOSANITARIO":
            return "Fitosanitario"
        if t == "SIEMBRA":
            return "Siembra"
        if t == "RECOLECCION":
            return "Cosecha"
        if t == "OTRAS":
            return "Otras"
        return (tipo or "Operación").strip() or "Operación"

    def _op_badge_class(tipo: str | None) -> str:
        t = (tipo or "").upper().strip()
        if t == "RIEGO":
            return "bg-info"
        if t == "FERTILIZACION":
            return "bg-success"
        if t == "FITOSANITARIO":
            return "op-badge-fitos"
        if t == "SIEMBRA":
            return "bg-warning text-dark"
        if t == "RECOLECCION":
            return "bg-primary"
        if t == "OTRAS":
            return "bg-secondary"
        return "bg-secondary"

    def _procedencia_agua_to_text(v) -> str:
        if not v:
            return ""
        arr = v if isinstance(v, list) else [v]
        out = []
        for x in arr:
            if not isinstance(x, dict):
                continue
            lab = (x.get("label") or x.get("codigo") or "").strip()
            if lab:
                out.append(lab)
        return ", ".join(out)

    def _op_resumen(tipo: str | None, detalle, descripcion: str | None) -> str:
        t = (tipo or "").upper().strip()
        d = detalle
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                d = {}
        if not isinstance(d, dict):
            d = {}

        if t == "RIEGO":
            v = d.get("volumen_m3", d.get("volumen"))
            try:
                txt_v = f"{float(v):.0f} m³" if v not in (None, "") else "—"
            except Exception:
                txt_v = "—"
            sis = (d.get("sistema_riego") or {}).get("label") or (d.get("sistema_riego") or {}).get("codigo") or ""
            proc = _procedencia_agua_to_text(d.get("procedencia_agua"))
            obs = (d.get("observaciones") or "").strip()
            parts = [txt_v]
            if sis:
                parts.append(sis)
            if proc:
                parts.append(proc)
            base = " · ".join([p for p in parts if p])
            return f"{base}{(' — ' + obs) if obs else ''}".strip()

        if t == "FERTILIZACION":
            prod = (d.get("producto") or {}).get("label") or (d.get("producto") or {}).get("codigo") or ""
            cant = d.get("cantidad")
            uni = (d.get("unidad") or "").strip()
            tipo_f = (d.get("tipo_fertilizacion") or {}).get("label") or (d.get("tipo_fertilizacion") or {}).get("codigo") or ""
            obs = (d.get("observaciones") or "").strip()
            txt_c = f"{cant} {uni}".strip() if cant not in (None, "") else "—"
            parts = [txt_c]
            if prod:
                parts.append(prod)
            if tipo_f:
                parts.append(tipo_f)
            base = " · ".join([p for p in parts if p])
            return f"{base}{(' — ' + obs) if obs else ''}".strip()
        
        if t == "FITOSANITARIO":
            prods = d.get("productos")

            if prods is None and d.get("producto") is not None:
                prods = d.get("producto")

            if isinstance(prods, dict):
                prods = [prods]
            if not isinstance(prods, list):
                prods = []

            def _s(v):
                return ("" if v is None else str(v)).strip()

            def _unit_text(u):
                if isinstance(u, dict):
                    return _s(u.get("label") or u.get("codigo"))
                if isinstance(u, str):
                    return u.strip()
                return ""

            def _one(p):
                if isinstance(p, str):
                    return p.strip() or "—"
                if not isinstance(p, dict):
                    return "—"

                prod = p.get("producto")
                prod = prod if isinstance(prod, dict) else {}

                label = _s(
                    prod.get("label")
                    or p.get("producto_nombre")
                    or p.get("nombre")
                    or p.get("formulado")
                )

                code = _s(
                    prod.get("codigo")
                    or p.get("producto_codigo")
                    or p.get("num_registro")
                    or p.get("numero_registro")
                )

                dosis = p.get("dosis")
                uni = _unit_text(p.get("unidad"))

                head = label or "—"
                if code and label:
                    head = f"{label} ({code})"
                elif code and not label:
                    head = code

                tail = ""
                if dosis not in (None, ""):
                    tail = f"{dosis} {uni}".strip()

                return " · ".join([x for x in (head, tail) if x]).strip() or "—"

            if not prods:
                return (descripcion or "—").strip() or "—"

            first = _one(prods[0])
            more = f" (+{len(prods)-1} más)" if len(prods) > 1 else ""
            return f"{first}{more}".strip()

        if t == "OTRAS":
            cat = (d.get("catalogo") or "").strip()
            lab = (d.get("label") or d.get("codigo") or "").strip()
            obs = (d.get("observaciones") or "").strip()
            base = " · ".join([p for p in [cat, lab] if p]).strip() or "—"
            return f"{base}{(' — ' + obs) if obs else ''}".strip()

        return (descripcion or "—").strip() or "—"

    operaciones_resumen = []
    for rec in recintos:
        rid = int(rec.id_recinto)
        nombre = (rec.nombre or "").strip()
        if not nombre:
            if rec.parcela is not None:
                nombre = f"Parcela {rec.parcela}"
            else:
                nombre = f"Recinto {rid}"

        ops = ops_by_recinto.get(rid, [])
        preview = []
        for op in ops:
            f = op.get("fecha")
            fecha_txt = f.strftime("%d/%m/%Y") if hasattr(f, "strftime") else (str(f) if f else "")
            tipo = op.get("tipo")
            preview.append({
                "tipo": tipo,
                "tipo_label": _op_tipo_label(tipo),
                "badge_class": _op_badge_class(tipo),
                "fecha": fecha_txt,
                "resumen": _op_resumen(tipo, op.get("detalle"), op.get("descripcion")),
            })

        operaciones_resumen.append({
            "id_recinto": rid,
            "nombre": nombre,
            "n_ops": len(ops),
            "ops": preview,
        })

    operaciones_resumen = [
        r for r in operaciones_resumen
        if r["n_ops"] > 0
    ]
    
    operaciones_resumen.sort(key=lambda x: (-int(x["n_ops"]), (x["nombre"] or "").lower()))

    # Obtener nombres reales usando tu clase utils_dashboard.py
    nombre_provincia = "Provincia"
    nombre_municipio = "Municipio"
    
    # codigo_municipio viene como "PPMMM" (ej: 34023)
    if codigo_municipio and len(codigo_municipio) == 5:
        c_pro = codigo_municipio[:2]
        c_mun = codigo_municipio[2:]
        
        # Usamos tus métodos existentes
        nombre_provincia = municipios_finder.obtener_nombre_provincia(c_pro) or nombre_provincia
        nombre_municipio = municipios_finder.obtener_nombre_municipio(c_pro, c_mun) or nombre_municipio

    # Solicitudes pendientes (solo para admin)
    pendientes = 0
    if getattr(current_user, "rol", None) in ("admin", "superadmin"):
        row = db.session.execute(text("""
            SELECT COUNT(*) AS n
            FROM public.solicitudes_recintos
            WHERE estado = 'pendiente'
        """)).mappings().first()
        pendientes = int(row["n"]) if row and row.get("n") is not None else 0
    alertas_riego = _fetch_alertas_riego_usuario(current_user.id_usuario)

    return render_template(
            'dashboard.html',
            username=current_user.username,
            url_widget=url_widget,
            weather=weather,
            codigo_municipio=codigo_municipio, 
            nombre_provincia=nombre_provincia,
            nombre_municipio=nombre_municipio,
            start_view=start_view,
            minimap_img_url=minimap_img_url,
            recintos_count=recintos_count,
            cultivo_principal=cultivo_principal,
            operaciones_resumen=operaciones_resumen,
            admin_solicitudes_pendientes=pendientes,
            is_admin=getattr(current_user, "rol", None) in ["admin", "superadmin"],
            alertas_riego=alertas_riego
        )

@dashboard_bp.route("/visor")
@login_required
def visor():
    """
    Vista del visor SIG. Calcula la bbox de la ROI a partir de sigpac.recintos
    y la pasa al template como roi_bbox = [minx, miny, maxx, maxy].
    
    Si se recibe recinto_id como parámetro, también envía los datos de ese recinto específico.
    """
    from flask import request
    
    # Obtener el ID del recinto si viene como parámetro
    recinto_id = request.args.get('recinto_id', type=int)
    recinto_data = None
    
    # Si hay un recinto específico, obtener sus datos y geometría
    if recinto_id:
        
        
        # Obtener el recinto del ORM
        recinto = Recinto.query.get(recinto_id)
        
        if recinto:
            sql_recinto = text("""
                SELECT
                    ST_XMin(geom) AS minx,
                    ST_YMin(geom) AS miny,
                    ST_XMax(geom) AS maxx,
                    ST_YMax(geom) AS maxy,
                    ST_AsGeoJSON(geom) AS geojson,
                    ST_Area(geography(geom)) / 10000.0 AS superficie_geom
                FROM public.recintos
                WHERE id_recinto = :rid
            """)

            geom_row = db.session.execute(sql_recinto, {'rid': recinto_id}).fetchone()
            
            if geom_row:
                # Obtener el propietario del ORM
                propietario = 'N/A'
                if hasattr(recinto, 'id_propietario') and recinto.id_propietario:
                    if recinto.propietario:
                        propietario = recinto.propietario.username
                nombre_provincia = municipios_finder.obtener_nombre_provincia(recinto.provincia)
                nombre_recinto = municipios_finder.obtener_nombre_municipio(recinto.provincia, recinto.municipio)
                sup_geom = (
                    float(geom_row.superficie_geom) if geom_row.superficie_geom is not None
                    else float(recinto.superficie_ha) if recinto.superficie_ha else 0
                )
                recinto_data = {
                    'id': recinto_id,
                    'provincia': recinto.provincia,
                    'municipio': recinto.municipio,
                    'poligono': recinto.poligono,
                    'parcela': recinto.parcela,
                    'recinto': recinto.recinto,
                    'nombre_provincia': nombre_provincia,
                    'nombre_municipio': nombre_recinto,
                    'nombre': recinto.nombre if recinto.nombre else f'Recinto {recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}-{recinto.recinto}',
                    'superficie_ha': round(sup_geom, 4),
                    'propietario': propietario,
                    'bbox': [geom_row.minx, geom_row.miny, geom_row.maxx, geom_row.maxy],
                    'geojson': geom_row.geojson
                }
    
    # Calcular bbox general (para vista inicial si no hay recinto específico)
    sql = text("""
        SELECT
            ST_XMin(extent) AS minx,
            ST_YMin(extent) AS miny,
            ST_XMax(extent) AS maxx,
            ST_YMax(extent) AS maxy
        FROM (
            SELECT ST_Extent(geometry) AS extent
            FROM sigpac.recintos
        ) sub;
    """)

    row = db.session.execute(sql).fetchone()

    if row and all(v is not None for v in row):
        roi_bbox = [row.minx, row.miny, row.maxx, row.maxy]
    else:
        # Fallback por si la consulta no devuelve nada
        roi_bbox = [-4.6718708208, 41.7248613835,
                    -3.8314839480, 42.1274665349]
        
    project_root = Path(__file__).resolve().parents[3]  # 2 niveles arriba


    ndvi_tif = os.path.join(project_root, "data", "raw", "ndvi_composite", "ndvi_latest_3857.tif")
    ndvi_bounds = leaflet_bounds_from_tif(ndvi_tif)

    municipios_codigos_finder = MunicipiosCodigosFinder()
    codigo_municipio_ine = municipios_codigos_finder.codigo_recintos_ine(current_user.id_usuario)

    weather = obtener_datos_aemet(codigo_municipio_ine)

    # --- Sentinel-2 RGB (mosaico reciente) ---
    meta_path = Path(current_app.root_path) / "static" / "sentinel2" / "s2_rgb_latest.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    s2_bounds = meta["bounds_leaflet"]
    s2_version = meta["updated_utc"]  # para bust cache
    
    # --- NDVI (mosaico reciente) ---
    ndvi_path = os.path.join(current_app.root_path, "static", "ndvi", "ndvi_latest.png")
    ndvi_version = int(os.path.getmtime(ndvi_path)) if os.path.exists(ndvi_path) else 0
    
    # Pasar recinto_data al template
    return render_template("visor.html", 
                         roi_bbox=roi_bbox, 
                         ndvi_bounds=ndvi_bounds,
                         weather=weather,
                         recinto_data=recinto_data,
                         s2_bounds=s2_bounds,
                         s2_version=s2_version,
                         ndvi_version=ndvi_version)

@dashboard_bp.route('/recinto/<int:id_recinto>')
@login_required
def detalle_recinto(id_recinto):
    recinto = Recinto.query.get_or_404(id_recinto)
    return render_template('detalle_recinto.html', recinto=recinto)


@dashboard_bp.route("/plan-cultivo")
@login_required
def plan_cultivo():
    """Listado de recintos del usuario con su cultivo y sus subparcelas."""
    uid = current_user.id_usuario
    recintos = (
        Recinto.query
        .filter(Recinto.id_propietario == uid)
        .order_by(Recinto.poligono, Recinto.parcela, Recinto.recinto)
        .all()
    )
    plan, total_ha = _datos_plan_cultivo(recintos)
    return render_template(
        "plan_cultivo.html",
        plan=plan,
        total_ha=total_ha,
        es_admin=False,
        volver_url=url_for("dashboard.dashboard"),
        descargar_shp_url=url_for("dashboard.plan_cultivo_descargar_shp"),
    )


def _datos_plan_cultivo(recintos, usuarios_por_id: dict | None = None) -> tuple[list, float]:
    """Construye filas del plan de cultivo (usuario o admin)."""
    ids = [r.id_recinto for r in recintos]
    area_geom_por_recinto = superficie_geom_por_recinto(ids)

    subparcelas_por_recinto: dict[int, list[dict]] = defaultdict(list)
    if ids:
        rows_sub = db.session.execute(
            text("""
                SELECT
                    s.id_subparcela,
                    s.id_recinto,
                    s.nombre,
                    s.superficie_ha,
                    s.cod_producto,
                    pf.descripcion AS cultivo
                FROM public.subparcelas s
                LEFT JOIN public.productos_fega pf ON pf.codigo = s.cod_producto
                WHERE s.id_recinto = ANY(:ids)
                ORDER BY s.id_subparcela
            """),
            {"ids": ids},
        ).mappings().all()
        for s in rows_sub:
            subparcelas_por_recinto[int(s["id_recinto"])].append({
                "nombre": (s["nombre"] or "").strip(),
                "superficie_ha": float(s["superficie_ha"]) if s["superficie_ha"] else 0.0,
                "cultivo": (s["cultivo"] or "").strip(),
            })

    cultivo_por_recinto: dict[int, str] = {}
    if ids:
        try:
            rows_cul = db.session.execute(
                text("""
                    SELECT DISTINCT ON (c.id_recinto)
                        c.id_recinto,
                        COALESCE(
                            NULLIF(BTRIM(pf.descripcion), ''),
                            NULLIF(BTRIM(c.tipo_cultivo), ''),
                            NULLIF(BTRIM(c.cultivo_custom), ''),
                            NULLIF(BTRIM(c.uso_sigpac), '')
                        ) AS cultivo
                    FROM public.cultivos c
                    LEFT JOIN public.productos_fega pf ON pf.codigo = c.cod_producto
                    WHERE c.id_recinto = ANY(:ids)
                      AND c.id_padre IS NOT NULL
                      AND COALESCE(c.estado, '') <> 'eliminado'
                    ORDER BY
                        c.id_recinto,
                        COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC NULLS LAST,
                        c.id_cultivo DESC
                """),
                {"ids": ids},
            ).mappings().all()
            for c in rows_cul:
                if c["cultivo"]:
                    cultivo_por_recinto[int(c["id_recinto"])] = str(c["cultivo"]).strip()
        except Exception:
            current_app.logger.exception("Error obteniendo cultivos para plan-cultivo")

    plan = []
    for r in recintos:
        rid = int(r.id_recinto)
        subs = subparcelas_por_recinto.get(rid, [])
        sup_geom = area_geom_por_recinto.get(
            rid, float(r.superficie_ha) if r.superficie_ha else 0.0
        )
        item = {
            "id_recinto": rid,
            "nombre": (r.nombre or "").strip() or f"Recinto {rid}",
            "poligono": r.poligono,
            "parcela": r.parcela,
            "superficie_ha": round(sup_geom, 4),
            "nombre_provincia": r.nombre_provincia,
            "nombre_municipio": r.nombre_municipio,
            "cultivo": cultivo_por_recinto.get(rid, ""),
            "subparcelas": subs,
            "n_subparcelas": len(subs),
        }
        if usuarios_por_id is not None:
            uid = r.id_propietario
            item["usuario"] = usuarios_por_id.get(uid, "—") if uid else "—"
        plan.append(item)

    total_ha = sum(p["superficie_ha"] for p in plan)
    return plan, total_ha


def _sql_cultivo_recinto_lateral():
    return """
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                NULLIF(BTRIM(pf2.descripcion), ''),
                NULLIF(BTRIM(c.tipo_cultivo), ''),
                NULLIF(BTRIM(c.cultivo_custom), '')
            ) AS cultivo
            FROM public.cultivos c
            LEFT JOIN public.productos_fega pf2 ON pf2.codigo = c.cod_producto
            WHERE c.id_recinto = r.id_recinto
              AND c.id_padre IS NOT NULL
              AND COALESCE(c.estado, '') NOT IN ('eliminado', 'cerrado')
            ORDER BY COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC NULLS LAST, c.id_cultivo DESC
            LIMIT 1
        ) pc ON true
    """


def _plan_cultivo_gdf_desde_features(features):
    """Construye GeoDataFrame listo para exportar (2D, campos compatibles con SHP)."""
    import geopandas as gpd
    from shapely.geometry import shape
    from shapely.ops import transform

    from shapely.geometry import MultiPolygon

    def _geom_2d(geom_json):
        geom = shape(geom_json)
        if geom.is_empty:
            return None
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        elif geom.geom_type != "MultiPolygon":
            return None
        if getattr(geom, "has_z", False) and geom.has_z:
            geom = transform(lambda x, y, z=None: (x, y), geom)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom if not geom.is_empty else None

    records = []
    geoms = []
    for feat in features:
        geom = _geom_2d(feat["geometry"])
        if geom is None:
            continue
        p = feat["properties"]
        records.append({
            "id_rec": int(p["id_rec"]),
            "id_sub": int(p["id_sub"]),
            "nombre": str(p["nombre"] or "")[:80],
            "poligono": str(p["poligono"]),
            "parcela": str(p["parcela"]),
            "recinto": str(p["recinto"]),
            "cultivo": str(p["cultivo"] or "")[:80],
            "ha": float(p["ha"]),
            "tipo": str(p["tipo"] or "")[:10],
            **({"usuario": str(p.get("usuario") or "")[:40]} if p.get("usuario") is not None else {}),
        })
        geoms.append(geom)

    if not geoms:
        return None
    return gpd.GeoDataFrame(records, geometry=geoms, crs="EPSG:4326")


def _zip_exportacion_gdf(gdf, basename: str = "plan_cultivo") -> io.BytesIO | None:
    """Escribe SHP (o GPKG si falla) en un ZIP en memoria."""
    tmpdir = tempfile.mkdtemp(prefix="plan_cultivo_")
    shp_path = os.path.abspath(os.path.join(tmpdir, f"{basename}.shp"))
    gpkg_path = os.path.abspath(os.path.join(tmpdir, f"{basename}.gpkg"))

    def _listar_exportados() -> list[str]:
        return [
            os.path.join(tmpdir, name)
            for name in os.listdir(tmpdir)
            if name.startswith(f"{basename}.")
            and os.path.isfile(os.path.join(tmpdir, name))
            and os.path.getsize(os.path.join(tmpdir, name)) > 0
        ]

    export_files: list[str] = []
    for kwargs in ({"encoding": "utf-8"}, {}):
        try:
            gdf.to_file(shp_path, driver="ESRI Shapefile", **kwargs)
        except Exception:
            logger.warning("Exportación SHP falló (kwargs=%s)", kwargs, exc_info=True)
        export_files = _listar_exportados()
        if export_files:
            break

    if not export_files:
        try:
            gdf.to_file(gpkg_path, driver="GPKG")
        except Exception:
            logger.warning("Exportación GPKG falló", exc_info=True)
        export_files = _listar_exportados()

    if not export_files:
        try:
            geojson_path = os.path.join(tmpdir, f"{basename}.geojson")
            with open(geojson_path, "w", encoding="utf-8") as fh:
                fh.write(gdf.to_json())
            if os.path.getsize(geojson_path) > 0:
                export_files = [geojson_path]
        except Exception:
            logger.exception("Exportación GeoJSON también falló")

    if not export_files:
        logger.error(
            "Sin archivos exportados (tmpdir=%s, filas=%s)",
            tmpdir,
            len(gdf),
        )
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in export_files:
            zf.write(fpath, arcname=os.path.basename(fpath))
    buf.seek(0)
    return buf


def _features_plan_cultivo_shp(uid: int | None = None, incluir_usuario: bool = False) -> list:
    """GeoJSON features para exportar SHP (un usuario o todos si uid es None)."""
    from shapely.geometry import shape

    cultivo_lat = _sql_cultivo_recinto_lateral()
    filtro_uid = "AND r.id_propietario = :uid" if uid is not None else "AND r.id_propietario IS NOT NULL"
    usuario_sel = ", COALESCE(u.username, '') AS usuario" if incluir_usuario else ""
    usuario_join = "LEFT JOIN public.usuarios u ON u.id_usuario = r.id_propietario" if incluir_usuario else ""

    sql = text(f"""
        SELECT
            r.id_recinto,
            s.id_subparcela,
            COALESCE(NULLIF(BTRIM(s.nombre), ''), r.nombre, 'Recinto ' || r.id_recinto::text) AS nombre,
            r.poligono,
            r.parcela,
            r.recinto,
            COALESCE(pf.descripcion, pc.cultivo, '') AS cultivo,
            ROUND(COALESCE(s.superficie_ha, r.superficie_ha, 0)::numeric, 4) AS ha,
            'subparcela'::text AS tipo,
            ST_AsGeoJSON(COALESCE(s.geom, r.geom))::json AS geom_json
            {usuario_sel}
        FROM public.recintos r
        INNER JOIN public.subparcelas s ON s.id_recinto = r.id_recinto
        LEFT JOIN public.productos_fega pf ON pf.codigo = s.cod_producto
        {usuario_join}
        {cultivo_lat}
        WHERE COALESCE(s.geom, r.geom) IS NOT NULL
          {filtro_uid}

        UNION ALL

        SELECT
            r.id_recinto,
            NULL::integer AS id_subparcela,
            COALESCE(NULLIF(BTRIM(r.nombre), ''), 'Recinto ' || r.id_recinto::text) AS nombre,
            r.poligono,
            r.parcela,
            r.recinto,
            COALESCE(pc.cultivo, '') AS cultivo,
            ROUND(COALESCE(r.superficie_ha, 0)::numeric, 4) AS ha,
            'recinto'::text AS tipo,
            ST_AsGeoJSON(r.geom)::json AS geom_json
            {usuario_sel}
        FROM public.recintos r
        {usuario_join}
        {cultivo_lat}
        WHERE r.geom IS NOT NULL
          {filtro_uid}
          AND NOT EXISTS (
              SELECT 1 FROM public.subparcelas sx WHERE sx.id_recinto = r.id_recinto
          )
    """)

    params = {"uid": uid} if uid is not None else {}
    rows = db.session.execute(sql, params).mappings().all()

    features = []
    for row in rows:
        geom_json = row.get("geom_json")
        if not geom_json:
            continue
        if isinstance(geom_json, str):
            try:
                geom_json = json.loads(geom_json)
            except json.JSONDecodeError:
                continue
        try:
            if shape(geom_json).is_empty:
                continue
        except Exception:
            continue
        props = {
            "id_rec": int(row["id_recinto"]),
            "id_sub": int(row["id_subparcela"]) if row["id_subparcela"] is not None else -1,
            "nombre": str(row["nombre"] or "")[:254],
            "poligono": int(row["poligono"]) if row["poligono"] is not None else 0,
            "parcela": int(row["parcela"]) if row["parcela"] is not None else 0,
            "recinto": int(row["recinto"]) if row["recinto"] is not None else 0,
            "cultivo": str(row["cultivo"] or "")[:254],
            "ha": float(row["ha"]) if row["ha"] is not None else 0.0,
            "tipo": str(row["tipo"] or ""),
        }
        if incluir_usuario:
            props["usuario"] = str(row.get("usuario") or "")[:40]
        features.append({
            "type": "Feature",
            "geometry": geom_json,
            "properties": props,
        })
    return features


def _respuesta_zip_plan_cultivo(features, download_name: str = "plan_cultivo.zip"):
    if not features:
        return jsonify({"error": "No hay geometrías para exportar"}), 404
    gdf = _plan_cultivo_gdf_desde_features(features)
    if gdf is None or gdf.empty:
        return jsonify({"error": "No hay geometrías válidas para exportar"}), 404
    buf = _zip_exportacion_gdf(gdf)
    if buf is None:
        return jsonify({"error": "No se generaron archivos del shapefile"}), 500
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_name,
    )


@dashboard_bp.route("/plan-cultivo/descargar-shp")
@login_required
def plan_cultivo_descargar_shp():
    """Exporta recintos/subparcelas del usuario a shapefile (ZIP)."""
    try:
        import geopandas  # noqa: F401
        from shapely.geometry import shape  # noqa: F401
    except ImportError:
        return jsonify({"error": "geopandas/shapely no disponible en el servidor"}), 500

    try:
        features = _features_plan_cultivo_shp(current_user.id_usuario)
    except Exception:
        logger.exception("Error leyendo geometrías para SHP")
        return jsonify({"error": "No se pudieron leer las geometrías"}), 500

    try:
        return _respuesta_zip_plan_cultivo(features)
    except Exception:
        logger.exception("Error generando SHP plan cultivo")
        return jsonify({"error": "Error generando el shapefile"}), 500


def _fecha_prediccion_riego(offset: str = "0") -> str:
    try:
        path = Path(current_app.root_path) / "static" / "riego_prediccion" / "indice.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data.get(offset, "") or "")
    except Exception:
        pass
    return ""


def _estado_riego(color: str | None) -> tuple[str, str]:
    """Estado según color del mapa (mismo criterio que ET de referencia: rojo/azul)."""
    c = (color or "").strip().lower()
    if c in ("red", "orange"):
        return "Riego recomendado", "danger"
    if c in ("blue", "none"):
        return "Sin recomendación", "primary"
    return "Sin datos de predicción", "secondary"


# Join espacial: celda de riego + color ET referencia (misma celda / criterio rojo-azul)
_SQL_LATERAL_RIEGO = """
        LEFT JOIN LATERAL (
            SELECT rp2.*
            FROM public.riego_prediccion_0 rp2
            WHERE ST_Intersects(r.geom, rp2.geometry)
            ORDER BY COALESCE(ST_Area(ST_Intersection(r.geom, rp2.geometry)), 0) DESC
            LIMIT 1
        ) rp ON true
        LEFT JOIN LATERAL (
            SELECT ep2.color AS color_etp
            FROM public.etp_prediccion_0 ep2
            WHERE ST_Intersects(r.geom, ep2.geometry)
            ORDER BY COALESCE(ST_Area(ST_Intersection(r.geom, ep2.geometry)), 0) DESC
            LIMIT 1
        ) ep ON true
"""


def _fetch_alertas_riego_usuario(uid: int) -> list[dict]:
    """Parcelas con riego recomendado (rojo en mapa ET / riego)."""
    if not _riego_prediccion_columnas():
        return []

    sql = text(f"""
        SELECT
            r.id_recinto,
            r.nombre,
            pf.descripcion AS cultivo,
            c.parc_sistexp,
            ROUND(COALESCE(r.superficie_ha, 0)::numeric, 2) AS superficie_ha,
            rp.riego_mm,
            COALESCE(rp.color, ep.color_etp) AS color,
            rp.fecha
        FROM public.recintos r
        LEFT JOIN sigpac.cultivo_declarado c
            ON r.provincia  = c.provincia
            AND r.municipio = c.municipio
            AND COALESCE(r.agregado, 0) = COALESCE(c.agregado, 0)
            AND COALESCE(r.zona, 0) = COALESCE(c.zona, 0)
            AND r.poligono  = c.poligono
            AND r.parcela   = c.parcela
            AND r.recinto   = c.recinto
        LEFT JOIN public.productos_fega pf ON c.parc_producto = pf.codigo
        {_SQL_LATERAL_RIEGO}
        WHERE r.id_propietario = :uid
          AND (r.activa IS TRUE OR r.activa IS NULL)
          AND rp.riego_mm IS NOT NULL
          AND TRIM(COALESCE(c.parc_sistexp, '')) = 'R'
          AND LOWER(COALESCE(rp.color, ep.color_etp, '')) IN ('red', 'orange')
        ORDER BY rp.riego_mm DESC NULLS LAST
        LIMIT 8
    """)

    try:
        rows = db.session.execute(sql, {"uid": uid}).mappings().all()
    except Exception:
        logger.exception("Error consultando alertas de riego")
        db.session.rollback()
        return []

    out = []
    for row in rows:
        demanda = float(row["riego_mm"] or 0)
        nombre = (row["nombre"] or "").strip() or f"Recinto {row['id_recinto']}"
        sistexp = "Regadío" if (row["parc_sistexp"] or "").strip() == "R" else "Secano"
        out.append({
            "id_recinto": row["id_recinto"],
            "nombre": nombre,
            "cultivo": (row["cultivo"] or "").strip() or "—",
            "superficie_ha": float(row["superficie_ha"] or 0),
            "sistexp": sistexp,
            "etc": round(demanda, 2),
            "fecha": row["fecha"] or _fecha_prediccion_riego("0"),
        })
    return out


def _riego_prediccion_columnas() -> set[str]:
    try:
        return set(
            db.session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'riego_prediccion_0'
            """)).scalars().all()
        )
    except Exception:
        db.session.rollback()
        return set()


def _fetch_dosis_riego_usuario(uid: int) -> list[dict]:
    cols = _riego_prediccion_columnas()
    tiene_riego = bool(cols)

    deficit_expr = (
        "COALESCE(NULLIF(rp.deficit_mm, 0), rp.riego_mm, 0)::numeric"
        if "deficit_mm" in cols and "riego_mm" in cols
        else ("COALESCE(rp.riego_mm, 0)::numeric" if "riego_mm" in cols else "0::numeric")
    )
    m3_expr = "COALESCE(rp.m3_ha, 0)::numeric" if "m3_ha" in cols else "0::numeric"
    cultivo_expr = "COALESCE(pf.descripcion, rp.cultivo)" if tiene_riego else "pf.descripcion"
    sistexp_expr = "c.parc_sistexp"

    lateral_join = ""
    riego_select = """
            NULL::double precision AS etp,
            NULL::double precision AS kc,
            NULL::double precision AS riego_mm,
            0::numeric AS deficit_mm,
            0::numeric AS m3_ha,
            NULL::text AS color,
            NULL::text AS fecha
    """
    if tiene_riego:
        lateral_join = _SQL_LATERAL_RIEGO
        riego_select = f"""
            rp.etp,
            rp.kc,
            rp.riego_mm,
            {deficit_expr} AS deficit_mm,
            {m3_expr} AS m3_ha,
            rp.color,
            ep.color_etp,
            rp.fecha
        """

    sql = text(f"""
        SELECT
            r.id_recinto,
            r.nombre,
            r.poligono,
            r.parcela,
            {cultivo_expr} AS cultivo,
            {sistexp_expr} AS sistexp_cod,
            ROUND(COALESCE(r.superficie_ha, 0)::numeric, 2) AS superficie_ha,
            {riego_select}
        FROM public.recintos r
        LEFT JOIN sigpac.cultivo_declarado c
            ON r.provincia  = c.provincia
            AND r.municipio = c.municipio
            AND COALESCE(r.agregado, 0) = COALESCE(c.agregado, 0)
            AND COALESCE(r.zona, 0) = COALESCE(c.zona, 0)
            AND r.poligono  = c.poligono
            AND r.parcela   = c.parcela
            AND r.recinto   = c.recinto
        LEFT JOIN public.productos_fega pf ON c.parc_producto = pf.codigo
        {lateral_join}
        WHERE r.id_propietario = :uid
          AND (r.activa IS TRUE OR r.activa IS NULL)
          AND TRIM(COALESCE(c.parc_sistexp, '')) = 'R'
        ORDER BY r.nombre NULLS LAST, r.id_recinto
    """)

    try:
        rows = db.session.execute(sql, {"uid": uid}).mappings().all()
    except Exception:
        logger.exception("Error consultando dosis de riego")
        db.session.rollback()
        sql_basico = text("""
            SELECT
                r.id_recinto,
                r.nombre,
                r.poligono,
                r.parcela,
                pf.descripcion AS cultivo,
                c.parc_sistexp AS sistexp_cod,
                ROUND(COALESCE(r.superficie_ha, 0)::numeric, 2) AS superficie_ha,
                NULL::double precision AS etp,
                NULL::double precision AS kc,
                NULL::double precision AS riego_mm,
                0::numeric AS deficit_mm,
                0::numeric AS m3_ha,
                NULL::text AS color,
                NULL::text AS fecha
            FROM public.recintos r
            LEFT JOIN sigpac.cultivo_declarado c
                ON r.provincia  = c.provincia
                AND r.municipio = c.municipio
                AND COALESCE(r.agregado, 0) = COALESCE(c.agregado, 0)
                AND COALESCE(r.zona, 0) = COALESCE(c.zona, 0)
                AND r.poligono  = c.poligono
                AND r.parcela   = c.parcela
                AND r.recinto   = c.recinto
            LEFT JOIN public.productos_fega pf ON c.parc_producto = pf.codigo
            WHERE r.id_propietario = :uid
              AND (r.activa IS TRUE OR r.activa IS NULL)
              AND TRIM(COALESCE(c.parc_sistexp, '')) = 'R'
            ORDER BY r.nombre NULLS LAST, r.id_recinto
        """)
        rows = db.session.execute(sql_basico, {"uid": uid}).mappings().all()

    out = []
    for row in rows:
        # Descartar recintos sin predicción de riego
        if row["riego_mm"] is None:
            continue

        nombre = (row["nombre"] or "").strip() or f"Recinto {row['id_recinto']}"
        sistexp = "Regadío" if (row["sistexp_cod"] or "").strip() == "R" else "Secano"
        etc = float(row["riego_mm"] or 0)
        deficit = float(row["deficit_mm"] or 0)
        demanda_mm = max(etc, deficit)
        color_mapa = row.get("color") or row.get("color_etp")
        estado, badge = _estado_riego(color_mapa)
        superficie_ha = float(row["superficie_ha"] or 0)
        superficie_m2 = superficie_ha * 10_000

        # m³/ha neto (déficit ETc - lluvia efectiva)
        m3_ha = float(row["m3_ha"] or 0)
        if m3_ha <= 0 and demanda_mm > 0:
            m3_ha = round(demanda_mm * 10, 1)    # 1 mm × 10 m³/ha

        # Litros y m³ totales para la parcela (sin factor de eficiencia)
        litros_netos   = round(demanda_mm * superficie_m2, 0)  # L = mm × m²
        m3_total_neto  = round(litros_netos / 1000, 1)

        # Aporte bruto ajustado por eficiencia estimada según tipo de sistema:
        # goteo/riego localizado → 92 %, aspersión → 78 %; por defecto (secano no regadío) → 85 %
        eficiencia = 0.92 if sistexp == "Regadío" else 0.85
        litros_brutos  = round(litros_netos / eficiencia, 0) if litros_netos > 0 else 0
        m3_total_bruto = round(litros_brutos / 1000, 1)

        out.append({
            "id_recinto":    row["id_recinto"],
            "nombre":        nombre,
            "poligono":      row["poligono"],
            "parcela":       row["parcela"],
            "cultivo":       (row["cultivo"] or "").strip() or "—",
            "sistexp":       sistexp,
            "superficie_ha": superficie_ha,
            "etp":           float(row["etp"]) if row["etp"] is not None else None,
            "kc":            float(row["kc"]) if row["kc"] is not None else None,
            "riego_mm":      etc,
            "deficit_mm":    demanda_mm,
            "m3_ha":         m3_ha,
            # Totales para la parcela completa
            "litros_netos":   int(litros_netos),
            "m3_total_neto":  m3_total_neto,
            "litros_brutos":  int(litros_brutos),
            "m3_total_bruto": m3_total_bruto,
            "eficiencia_pct": int(eficiencia * 100),
            "estado":        estado,
            "badge":         badge,
            "fecha":         row["fecha"] or _fecha_prediccion_riego("0"),
        })
    return out


@dashboard_bp.route("/dosis-riego")
@login_required
def dosis_riego():
    items = _fetch_dosis_riego_usuario(current_user.id_usuario)
    fecha_ref = _fecha_prediccion_riego("0")
    urgentes = sum(1 for i in items if i["badge"] == "danger")
    recomendados = sum(1 for i in items if i["badge"] == "warning")
    return render_template(
        "dosis_riego.html",
        items=items,
        fecha_ref=fecha_ref,
        urgentes=urgentes,
        recomendados=recomendados,
    )


@dashboard_bp.route("/contadores")
@login_required
def contadores():
    contadores = (
        Contador.query
        .join(Recinto, Contador.id_recinto == Recinto.id_recinto)
        .filter(Contador.id_usuario == current_user.id_usuario)
        .order_by(Contador.fecha_creacion.desc())
        .all()
    )

    return render_template("contadores.html", contadores=contadores)



def _norm(s: str) -> str:
    """Normaliza texto: mayúsculas, sin tildes."""
    return unicodedata.normalize("NFD", (s or "").upper()).encode("ascii", "ignore").decode()


def _estimar_cosecha(cultivo: str, tipo_registro: str, fecha_inicio: date | None) -> date | None:
    """
    Recalcula la fecha de cosecha estimada usando el nombre del cultivo.
    Se usa para corregir fechas antiguas calculadas con la lógica genérica (siembra+365).
    Devuelve None si no hay suficiente información.
    """
    if not fecha_inicio:
        return None

    n = _norm(cultivo)

    if tipo_registro == "PLANTACION":
        # Cultivos permanentes: próxima fecha anual típica de cosecha
        hoy = date.today()
        ref = max(fecha_inicio, hoy)

        mes_dia = None
        if _re.search(r"OLIVO|OLIVAR", n):
            mes_dia = (11, 15)
        elif _re.search(r"VI[NÑ]A|VID|UVA", n):
            mes_dia = (9, 30)
        elif _re.search(r"ALMENDRO|AVELLANO|NOGAL|PISTACHO", n):
            mes_dia = (8, 31)
        elif _re.search(r"MANZANO|PERAL|MELOCOTO|CEREZO|CIRUELO|FRUTALES?", n):
            mes_dia = (9, 15)
        elif _re.search(r"NARANJA|LIMON|MANDARINA|CITRICO", n):
            mes_dia = (12, 15)

        if mes_dia:
            año = ref.year
            cand = date(año, mes_dia[0], mes_dia[1])
            if cand <= ref:
                cand = date(año + 1, mes_dia[0], mes_dia[1])
            return cand
        return None  # forestal u otro permanente sin cosecha definida

    # Cultivo anual (CAMPANA): duración típica desde fecha de siembra
    delta = 150  # defecto razonable
    if _re.search(r"TRIGO|CEBADA|AVENA|CENTENO|TRITICALE|ESPELTA|COLZA|MOSTAZA|CAMELINA", n):
        delta = 220
    elif _re.search(r"MAIZ|GIRASOL|CARTAMO|MIJO|SORGO|TEFF|QUINOA", n):
        delta = 140
    elif _re.search(r"GARBANZO|LENTEJA|VEZA|GUISANTE|HABA|ALUBIA|ALVERJON|ALMORTA|YEROS|TITARROS|ESPARCETA", n):
        delta = 160
    elif _re.search(r"PATATA|REMOLACHA", n):
        delta = 140
    elif _re.search(r"TOMATE|PEPINO|PIMIENTO|CALABAZA|MELON|SANDIA", n):
        delta = 110
    elif _re.search(r"AJO|CEBOLLA|ZANAHORIA", n):
        delta = 130
    elif _re.search(r"ALFALFA|FESTUCA|RAYGRASS|PRADERA|PASTOS|CULTIVOS MIXTOS", n):
        delta = 90
    elif _re.search(r"LAVANDA|LAVANDIN|ANIS", n):
        delta = 120

    return fecha_inicio + timedelta(days=delta)


def _estimar_rendimiento_kg_ha(cultivo: str, tipo_registro: str) -> float | None:
    """Rendimiento estimado en kg/ha según tipo de cultivo (referencias CyL)."""
    n = _norm(cultivo)
    if not n:
        return None

    if tipo_registro == "PLANTACION":
        if _re.search(r"OLIVO|OLIVAR", n):
            return 3500.0
        if _re.search(r"VI[NÑ]A|VID|UVA", n):
            return 8000.0
        if _re.search(r"ALMENDRO|AVELLANO|NOGAL|PISTACHO", n):
            return 2000.0
        if _re.search(r"MANZANO|PERAL|MELOCOTO|CEREZO|CIRUELO|FRUTALES?", n):
            return 25000.0
        if _re.search(r"NARANJA|LIMON|MANDARINA|CITRICO", n):
            return 30000.0
        return None

    if _re.search(r"TRIGO|CEBADA|CENTENO|TRITICALE|ESPELTA", n):
        return 3800.0
    if _re.search(r"MAIZ", n):
        return 11000.0
    if _re.search(r"GIRASOL|CARTAMO", n):
        return 2200.0
    if _re.search(r"GARBANZO|LENTEJA|VEZA|GUISANTE|HABA|ALUBIA", n):
        return 1800.0
    if _re.search(r"PATATA", n):
        return 35000.0
    if _re.search(r"REMOLACHA", n):
        return 60000.0
    if _re.search(r"COLZA|MOSTAZA|CAMELINA", n):
        return 2500.0
    if _re.search(r"TOMATE|PIMIENTO|PEPINO", n):
        return 70000.0
    if _re.search(r"ALFALFA|RAYGRASS|PRADERA|PASTOS", n):
        return 12000.0
    return 3000.0


def _prevision_cosecha_kg(cultivo: str, tipo_registro: str, superficie_ha: float, avanzado) -> dict | None:
    """Devuelve {kg_ha, kg_total} para mostrar previsión en kg."""
    if avanzado and isinstance(avanzado, dict):
        prev = avanzado.get("prevision_cosecha")
        if isinstance(prev, dict) and prev.get("kg_ha"):
            kg_ha = float(prev["kg_ha"])
            kg_total = prev.get("kg_total")
            if kg_total is None and superficie_ha:
                kg_total = round(kg_ha * superficie_ha, 0)
            return {"kg_ha": kg_ha, "kg_total": float(kg_total or 0)}

    kg_ha = _estimar_rendimiento_kg_ha(cultivo, tipo_registro)
    if kg_ha is None:
        return None
    kg_total = round(kg_ha * float(superficie_ha or 0), 0) if superficie_ha else None
    return {"kg_ha": kg_ha, "kg_total": kg_total}


@dashboard_bp.route("/cuaderno-campo")
@login_required
def cuaderno_campo():
    """Cuaderno de campo: lista de cultivos activos con operaciones recientes."""
    uid = current_user.id_usuario
    cutoff = date.today() - timedelta(days=60)

    sql = text("""
        WITH myrec AS (
            SELECT r.id_recinto, r.nombre, r.poligono, r.parcela, r.recinto
            FROM public.recintos r
            WHERE r.id_propietario = :uid
              AND (r.activa IS TRUE OR r.activa IS NULL)
        ),
        cultivos_activos AS (
            SELECT DISTINCT ON (c.id_recinto)
                c.id_cultivo,
                c.id_recinto,
                c.estado,
                c.tipo_registro,
                c.campana,
                c.variedad,
                COALESCE(
                    NULLIF(BTRIM(c.tipo_cultivo), ''),
                    NULLIF(BTRIM(c.cultivo_custom), ''),
                    NULLIF(BTRIM(pf.descripcion), ''),
                    NULLIF(BTRIM(c.uso_sigpac), '')
                ) AS cultivo,
                COALESCE(c.fecha_siembra, c.fecha_implantacion) AS fecha_inicio,
                COALESCE(c.fecha_cosecha_real, c.fecha_cosecha_estimada) AS fecha_fin,
                c.cosecha_estimada_auto,
                c.fecha_cosecha_real,
                c.avanzado
            FROM public.cultivos c
            JOIN myrec r ON r.id_recinto = c.id_recinto
            LEFT JOIN public.productos_fega pf ON pf.codigo = c.cod_producto
            WHERE c.id_padre IS NOT NULL
              AND COALESCE(c.estado, '') NOT IN ('eliminado', 'cerrado')
            ORDER BY c.id_recinto,
                COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC NULLS LAST,
                c.id_cultivo DESC
        )
        SELECT
            mr.id_recinto,
            COALESCE(NULLIF(BTRIM(mr.nombre), ''), 'Recinto ' || mr.id_recinto::text) AS recinto_nombre,
            mr.poligono,
            mr.parcela,
            mr.recinto AS recinto_num,
            ca.cultivo,
            ca.variedad,
            ca.estado,
            ca.tipo_registro,
            ca.campana,
            ca.fecha_inicio,
            ca.fecha_fin,
            ca.cosecha_estimada_auto,
            ca.fecha_cosecha_real,
            ca.avanzado,
            ST_Area(geography(r.geom)) / 10000.0 AS superficie_ha
        FROM myrec mr
        JOIN cultivos_activos ca ON ca.id_recinto = mr.id_recinto
        JOIN public.recintos r ON r.id_recinto = mr.id_recinto
        ORDER BY mr.poligono, mr.parcela, mr.recinto
    """)

    sql_ops = text("""
        SELECT
            o.id_recinto,
            t.codigo AS tipo,
            o.fecha,
            o.descripcion,
            o.detalle
        FROM public.operaciones o
        JOIN public.tipos_operacion t ON t.id_tipo_operacion = o.id_tipo_operacion
        JOIN public.recintos r ON r.id_recinto = o.id_recinto
        WHERE r.id_propietario = :uid
          AND (r.activa IS TRUE OR r.activa IS NULL)
          AND o.fecha >= :cutoff
        ORDER BY o.id_recinto, o.fecha DESC, o.id_operacion DESC
    """)

    def _tipo_label(t):
        m = {'RIEGO': 'Riego', 'FERTILIZACION': 'Fertilización', 'FITOSANITARIO': 'Fitosanitario',
             'SIEMBRA': 'Siembra', 'RECOLECCION': 'Cosecha', 'OTRAS': 'Otras'}
        return m.get((t or '').upper().strip(), t or 'Operación')

    def _badge(t):
        m = {'RIEGO': 'info', 'FERTILIZACION': 'success', 'FITOSANITARIO': 'warning',
             'SIEMBRA': 'secondary', 'RECOLECCION': 'primary', 'OTRAS': 'light text-dark'}
        return m.get((t or '').upper().strip(), 'secondary')

    ops_raw = db.session.execute(sql_ops, {"uid": uid, "cutoff": cutoff}).mappings().all()
    ops_by_recinto = defaultdict(list)
    for op in ops_raw:
        rid = int(op["id_recinto"])
        if len(ops_by_recinto[rid]) < 5:
            f = op.get("fecha")
            ops_by_recinto[rid].append({
                "tipo": op["tipo"],
                "tipo_label": _tipo_label(op["tipo"]),
                "badge": _badge(op["tipo"]),
                "fecha": f.strftime("%d/%m/%Y") if hasattr(f, "strftime") else (str(f) if f else ""),
            })

    items = []
    for row in db.session.execute(sql, {"uid": uid}).mappings().all():
        rid = int(row["id_recinto"])
        fi = row.get("fecha_inicio")
        fin_es_real = bool(row.get("fecha_cosecha_real"))
        cultivo_nombre = (row["cultivo"] or "").strip() or "Sin cultivo"
        tipo_reg = (row.get("tipo_registro") or "CAMPANA").strip().upper()
        sup_ha = float(row["superficie_ha"] or 0)
        avanzado = row.get("avanzado")
        if isinstance(avanzado, str):
            try:
                avanzado = json.loads(avanzado)
            except Exception:
                avanzado = None

        fin_es_real = bool(row.get("fecha_cosecha_real"))
        prevision = _prevision_cosecha_kg(cultivo_nombre, tipo_reg, sup_ha, avanzado)
        if not prevision:
            prevision = _prevision_cosecha_kg(cultivo_nombre, tipo_reg, sup_ha, None)

        items.append({
            "id_recinto":     rid,
            "recinto_nombre": row["recinto_nombre"],
            "poligono":       row["poligono"],
            "parcela":        row["parcela"],
            "recinto_num":    row["recinto_num"],
            "cultivo":        cultivo_nombre,
            "variedad":       (row["variedad"] or "").strip(),
            "estado":         (row["estado"] or "").strip(),
            "superficie_ha":  round(sup_ha, 2),
            "fecha_inicio":   fi.strftime("%d/%m/%Y") if hasattr(fi, "strftime") else (str(fi) if fi else ""),
            "fecha_fin": (
                (row.get("fecha_cosecha_real") or row.get("fecha_fin")).strftime("%d/%m/%Y")
                if hasattr(row.get("fecha_cosecha_real") or row.get("fecha_fin"), "strftime")
                else ""
            ),
            "fin_es_real":    fin_es_real,
            "prevision_kg_ha": round(prevision["kg_ha"], 0) if prevision else None,
            "prevision_kg_total": round(prevision["kg_total"], 0) if prevision and prevision.get("kg_total") else None,
            "operaciones":    ops_by_recinto.get(rid, []),
        })

    return render_template("cuaderno_campo.html", items=items)


@dashboard_bp.route('/contadores/eliminar/<int:id>', methods=['DELETE'])
@login_required
def eliminar_contador(id):
    contador = Contador.query.filter_by(id=id, id_usuario=current_user.id_usuario).first()
    if not contador:
        return jsonify({'error': 'No encontrado'}), 404

    import os
    for ruta in [contador.ruta_imagen, contador.ruta_thumb]:
        if ruta:
            ruta_abs = os.path.join(current_app.static_folder, ruta.lstrip('/static/'))
            try:
                os.remove(ruta_abs)
            except Exception:
                pass

    db.session.delete(contador)
    db.session.commit()
    return jsonify({'ok': True}), 200