from datetime import date, timedelta
from  pathlib import Path
from sqlalchemy import text
from webapp import db
from flask import render_template, current_app
from flask_login import login_required, current_user
from collections import defaultdict
from webapp.api.services import visor_start_view_usuario
from . import dashboard_bp
import json
import logging
from .utils_dashboard import leaflet_bounds_from_tif, obtener_datos_aemet, MunicipiosCodigosFinder
from ..models import Recinto
import os
from webapp.dashboard.utils_dashboard import municipios_finder


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
    municipios_codigos_finder = MunicipiosCodigosFinder()
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
            SELECT cur.cultivo, SUM(COALESCE(r.superficie_ha, 0)) AS ha
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
            return "bg-warning text-dark"
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
            # Construir la consulta SQL usando los campos SIGPAC como filtro
            # La tabla sigpac.recintos probablemente usa provincia, municipio, poligono, parcela, recinto como identificadores
            sql_recinto = text("""
                SELECT
                    ST_XMin(geometry) AS minx,
                    ST_YMin(geometry) AS miny,
                    ST_XMax(geometry) AS maxx,
                    ST_YMax(geometry) AS maxy,
                    ST_AsGeoJSON(geometry) AS geojson
                FROM sigpac.recintos
                WHERE provincia = :provincia
                  AND municipio = :municipio
                  AND poligono = :poligono
                  AND parcela = :parcela
                  AND recinto = :recinto
            """)
            
            geom_row = db.session.execute(sql_recinto, {
                'provincia': recinto.provincia,
                'municipio': recinto.municipio,
                'poligono': recinto.poligono,
                'parcela': recinto.parcela,
                'recinto': recinto.recinto
            }).fetchone()
            
            if geom_row:
                # Obtener el propietario del ORM
                propietario = 'N/A'
                if hasattr(recinto, 'id_propietario') and recinto.id_propietario:
                    if recinto.propietario:
                        propietario = recinto.propietario.username
                nombre_provincia = municipios_finder.obtener_nombre_provincia(recinto.provincia)
                nombre_recinto = municipios_finder.obtener_nombre_municipio(recinto.provincia, recinto.municipio)
                recinto_data = {
                    'id': recinto_id,  # Usamos el id del modelo ORM
                    'provincia': recinto.provincia,
                    'municipio': recinto.municipio,
                    'poligono': recinto.poligono,
                    'parcela': recinto.parcela,
                    'recinto': recinto.recinto,
                    'nombre_provincia': nombre_provincia,
                    'nombre_municipio': nombre_recinto,
                    'nombre': recinto.nombre if recinto.nombre else f'Recinto {recinto.provincia}-{recinto.municipio}-{recinto.poligono}-{recinto.parcela}-{recinto.recinto}',
                    'superficie_ha': float(recinto.superficie_ha) if recinto.superficie_ha else 0,
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