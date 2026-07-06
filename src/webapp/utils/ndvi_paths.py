"""Resolución de rutas NDVI composite (latest o más reciente fechado)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATED_STEM = re.compile(r"^ndvi_(\d{8})(?:_|\.png$)")


def ndvi_composite_dir(project_root: Path) -> Path:
    return project_root / "data" / "raw" / "ndvi_composite"


def _newest(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _dated_candidates(ndvi_dir: Path, pattern: str) -> list[Path]:
    return [p for p in ndvi_dir.glob(pattern) if "latest" not in p.name]


def resolve_ndvi_latest_3857(project_root: Path) -> Path | None:
    ndvi_dir = ndvi_composite_dir(project_root)
    candidates = [ndvi_dir / "ndvi_latest_3857.tif"]
    candidates.extend(_dated_candidates(ndvi_dir, "ndvi_*_3857.tif"))
    return _newest(candidates)


def resolve_ndvi_latest_png(project_root: Path) -> Path | None:
    ndvi_dir = ndvi_composite_dir(project_root)
    candidates = [ndvi_dir / "ndvi_latest.png"]
    candidates.extend(_dated_candidates(ndvi_dir, "ndvi_*.png"))
    return _newest(candidates)


def resolve_ndvi_latest_json(project_root: Path) -> Path | None:
    ndvi_dir = ndvi_composite_dir(project_root)
    png = resolve_ndvi_latest_png(project_root)
    if png and png.name != "ndvi_latest.png":
        m = _DATED_STEM.match(png.name)
        if m:
            dated_meta = ndvi_dir / f"ndvi_{m.group(1)}.json"
            if dated_meta.is_file():
                return dated_meta

    latest = ndvi_dir / "ndvi_latest.json"
    if latest.is_file():
        return latest

    dated = _dated_candidates(ndvi_dir, "ndvi_*.json")
    return _newest(dated)


def ndvi_date_display(project_root: Path) -> str | None:
    meta_path = resolve_ndvi_latest_json(project_root)
    if not meta_path:
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("date_display") or meta.get("temporal_range", {}).get("end")
    except (OSError, json.JSONDecodeError):
        return None
