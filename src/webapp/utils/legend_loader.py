# webapp/trazasytrazadas/utils/legend_loader.py
from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import Dict, List, Any


def _to_int(x, default=0) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02X}{g:02X}{b:02X}"


@lru_cache(maxsize=32)
def load_legend_from_csv(csv_path: str) -> Dict[str, Any]:
    """
    Lee CSV de codificación (código, descripción, R,G,B) y devuelve un JSON listo para frontend.
    Cacheado para no releer en cada request.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Legend CSV not found: {csv_path}")

    items: List[Dict[str, Any]] = []

    # Tu CSV suele venir con separador ';' y BOM utf-8.
    # Usamos csv.Sniffer con fallback a ';'.
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel
            dialect.delimiter = ";"

        reader = csv.DictReader(f, dialect=dialect)

        # Normalizamos nombres de columna que en tu CSV vienen con saltos de línea:
        # "Cod\nCultivo" y "Descripción \ncultivo"
        def pick(row: dict, keys: List[str]) -> str:
            for k in keys:
                if k in row and row[k] is not None:
                    return str(row[k]).strip()
            return ""

        for row in reader:
            code_raw = pick(row, ["Cod\nCultivo", "Cod Cultivo", "CodCultivo", "COD", "code"])
            label = pick(row, ["Descripción \ncultivo", "Descripción cultivo", "Descripcion cultivo", "label", "name"])
            r_raw = pick(row, ["R", "r", "Red"])
            g_raw = pick(row, ["G", "g", "Green"])
            b_raw = pick(row, ["B", "b", "Blue"])

            code = _to_int(code_raw, default=-1)
            r = _to_int(r_raw, default=0)
            g = _to_int(g_raw, default=0)
            b = _to_int(b_raw, default=0)

            if code == -1 or not label:
                # Saltamos filas incompletas
                continue

            items.append({
                "code": code,
                "label": label,
                "r": r,
                "g": g,
                "b": b,
                "hex": _rgb_to_hex(r, g, b),
            })

    items.sort(key=lambda x: x["code"])

    return {
        "source": os.path.basename(csv_path),
        "count": len(items),
        "items": items,
    }
