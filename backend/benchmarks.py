"""Regional NDVI benchmarks for vineyard comparison."""

from __future__ import annotations

from typing import Any


REGIONAL_NDVI_BASELINES: dict[str, dict[str, float | str]] = {
    "VALLE_DE_UCO": {
        "region": "Valle de Uco",
        "avg_ndvi": 0.62,
        "p10": 0.41,
        "p25": 0.50,
        "p50": 0.61,
        "p75": 0.73,
        "p90": 0.82,
    },
    "LUJAN_DE_CUYO": {
        "region": "Luján de Cuyo",
        "avg_ndvi": 0.58,
        "p10": 0.37,
        "p25": 0.46,
        "p50": 0.57,
        "p75": 0.69,
        "p90": 0.79,
    },
    "MAIPU": {
        "region": "Maipú",
        "avg_ndvi": 0.55,
        "p10": 0.34,
        "p25": 0.43,
        "p50": 0.54,
        "p75": 0.65,
        "p90": 0.75,
    },
    "EAST_MENDOZA": {
        "region": "Este de Mendoza",
        "avg_ndvi": 0.49,
        "p10": 0.29,
        "p25": 0.37,
        "p50": 0.48,
        "p75": 0.59,
        "p90": 0.69,
    },
    "SAN_RAFAEL": {
        "region": "San Rafael",
        "avg_ndvi": 0.57,
        "p10": 0.36,
        "p25": 0.45,
        "p50": 0.56,
        "p75": 0.67,
        "p90": 0.77,
    },
    "ALL_MENDOZA": {
        "region": "Mendoza (General)",
        "avg_ndvi": 0.56,
        "p10": 0.35,
        "p25": 0.44,
        "p50": 0.55,
        "p75": 0.67,
        "p90": 0.78,
    },
}


def _normalize_region(region: str) -> str:
    region_key = region.strip().upper().replace(" ", "_")
    return region_key


def get_region_baseline(region: str) -> dict[str, Any]:
    """Get benchmark baseline by region key or display name."""
    region_key = _normalize_region(region)
    baseline = REGIONAL_NDVI_BASELINES.get(region_key)
    if baseline:
        return {"region_key": region_key, **baseline}

    for key, candidate in REGIONAL_NDVI_BASELINES.items():
        if candidate["region"] == region:
            return {"region_key": key, **candidate}

    raise KeyError(f"Unknown benchmark region: {region}")


def list_benchmarks() -> dict[str, dict[str, float | str]]:
    """Return static regional benchmark definitions."""
    return REGIONAL_NDVI_BASELINES


def _interpolate_percentile(ndvi: float, baseline: dict[str, float | str]) -> float:
    points = [
        (10.0, float(baseline["p10"])),
        (25.0, float(baseline["p25"])),
        (50.0, float(baseline["p50"])),
        (75.0, float(baseline["p75"])),
        (90.0, float(baseline["p90"])),
    ]

    if ndvi <= points[0][1]:
        return 5.0
    if ndvi >= points[-1][1]:
        return 95.0

    for (p0, n0), (p1, n1) in zip(points, points[1:]):
        if n0 <= ndvi <= n1:
            if n1 == n0:
                return p1
            ratio = (ndvi - n0) / (n1 - n0)
            return p0 + ratio * (p1 - p0)

    return 50.0


def compute_regional_benchmark(
    ndvi: float,
    region_key: str | None = None,
    region_name: str | None = None,
) -> dict[str, Any]:
    """Compute benchmark comparison for an NDVI against a regional baseline."""
    selected_key = region_key if region_key in REGIONAL_NDVI_BASELINES else "ALL_MENDOZA"
    baseline = REGIONAL_NDVI_BASELINES[selected_key]
    percentile = _interpolate_percentile(ndvi, baseline)
    avg_ndvi = float(baseline["avg_ndvi"])

    return {
        "region": region_name or baseline["region"],
        "percentile_ndvi": round(percentile, 1),
        "delta_vs_region_avg": round(ndvi - avg_ndvi, 3),
    }
