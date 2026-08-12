"""Sentinel Hub utilities, NDVI history, and alert evaluation."""

import base64
import logging
import os
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException

from backend.time_window import build_time_window, format_iso_utc, parse_iso_datetime

logger = logging.getLogger("vitistrust")

SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")
SENTINEL_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
SENTINEL_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

_token_cache: dict[str, Any] = {"token": None, "expires": 0}

NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
  const ramp = [
    [-0.1, [100, 100, 100]], [0.1, [139, 69, 19]], [0.25, [218, 165, 32]],
    [0.45, [154, 205, 50]], [0.7, [34, 139, 34]], [0.9, [0, 100, 0]]
  ];
  for (let i = 0; i < ramp.length - 1; i++) {
    if (ndvi <= ramp[i+1][0]) {
      const t = (ndvi - ramp[i][0]) / (ramp[i+1][0] - ramp[i][0]);
      return [
        Math.round(ramp[i][1][0] + t * (ramp[i+1][1][0] - ramp[i][1][0])),
        Math.round(ramp[i][1][1] + t * (ramp[i+1][1][1] - ramp[i][1][1])),
        Math.round(ramp[i][1][2] + t * (ramp[i+1][1][2] - ramp[i][1][2])),
        255
      ];
    }
  }
  return [0, 100, 0, 255];
}
"""

NDMI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B08", "B11", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  let ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
  const ramp = [
    [-0.3, [139, 0, 0]], [0.0, [200, 150, 50]], [0.2, [100, 180, 200]],
    [0.4, [50, 100, 180]], [0.6, [0, 50, 100]]
  ];
  for (let i = 0; i < ramp.length - 1; i++) {
    if (ndmi <= ramp[i+1][0]) {
      const t = (ndmi - ramp[i][0]) / (ramp[i+1][0] - ramp[i][0]);
      return [
        Math.round(ramp[i][1][0] + t * (ramp[i+1][1][0] - ramp[i][1][0])),
        Math.round(ramp[i][1][1] + t * (ramp[i+1][1][1] - ramp[i][1][1])),
        Math.round(ramp[i][1][2] + t * (ramp[i+1][1][2] - ramp[i][1][2])),
        255
      ];
    }
  }
  return [0, 50, 100, 255];
}
"""

TRUE_COLOR_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B03", "B02", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  return [sample.B04, sample.B03, sample.B02, 255];
}
"""


async def _get_sentinel_token() -> str | None:
    now = time.time()

    if _token_cache["token"] and now < _token_cache["expires"] - 60:
        return _token_cache["token"]

    if not SENTINEL_CLIENT_ID or not SENTINEL_CLIENT_SECRET:
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SENTINEL_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": SENTINEL_CLIENT_ID,
                    "client_secret": SENTINEL_CLIENT_SECRET,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                _token_cache["token"] = data["access_token"]
                _token_cache["expires"] = now + data.get("expires_in", 3600)
                return _token_cache["token"]
    except Exception as exc:
        logger.warning("Sentinel OAuth token fetch failed: %s", exc)

    return None


async def _fetch_sentinel_image(
    token: str,
    lat: float,
    lon: float,
    evalscript: str = NDVI_EVALSCRIPT,
    date_from: str | None = None,
    date_to: str | None = None,
) -> bytes | None:
    offset = 0.005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]

    requested_from, requested_to = (
        (date_from, date_to) if date_from and date_to else build_time_window(180)
    )
    fallback_from, fallback_to = build_time_window(365)
    windows: list[tuple[str, str, str]] = [
        (requested_from, requested_to, "requested"),
        (fallback_from, fallback_to, "fallback-expanded"),
    ]

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            for current_from, current_to, window_label in windows:
                logger.info(
                    "Satellite image query window=%s from=%s to=%s lat=%s lon=%s",
                    window_label,
                    current_from,
                    current_to,
                    lat,
                    lon,
                )

                payload = {
                    "input": {
                        "bounds": {
                            "bbox": bbox,
                            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                        },
                        "data": [{
                            "type": "sentinel-2-l2a",
                            "dataFilter": {
                                "timeRange": {"from": current_from, "to": current_to},
                                "maxCloudCoverage": 20,
                            },
                        }],
                    },
                    "output": {
                        "responses": [{"identifier": "default", "format": {"type": "image/png"}}]
                    },
                    "evalscript": evalscript,
                }

                resp = await client.post(
                    SENTINEL_PROCESS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code == 200 and len(resp.content) > 500:
                    return resp.content
                logger.warning(
                    "Sentinel image empty for window=%s from=%s to=%s status=%s size=%s",
                    window_label,
                    current_from,
                    current_to,
                    resp.status_code,
                    len(resp.content),
                )
    except Exception as exc:
        logger.warning("Error downloading image: %s", exc)
    return None


def _resolve_window(
    date: str | None = None,
    from_param: str | None = None,
    to_param: str | None = None,
) -> tuple[str, str]:
    if from_param or to_param:
        if not from_param or not to_param:
            raise HTTPException(
                status_code=422,
                detail="Both 'from' and 'to' query params are required when overriding time window",
            )
        try:
            parsed_from = parse_iso_datetime(from_param)
            parsed_to = parse_iso_datetime(to_param)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid ISO datetime format for 'from'/'to': {exc}",
            ) from exc

        if parsed_from >= parsed_to:
            raise HTTPException(
                status_code=422,
                detail="'from' must be earlier than 'to'",
            )
        return format_iso_utc(parsed_from), format_iso_utc(parsed_to)

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
            return build_time_window(days_back=60, end=target_date + timedelta(days=30))
        except ValueError:
            logger.warning(
                "Invalid date format for /satellite-image date=%s, using default window",
                date,
            )

    return build_time_window(180)


def _generate_placeholder_svg(lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> bytes:
    if layer == "ndmi":
        health_color = "#3b82f6" if ndvi > 0.3 else "#f59e0b" if ndvi > 0.1 else "#ef4444"
        health_text = "Hydrated" if ndvi > 0.3 else "Moderate Stress" if ndvi > 0.1 else "Severe Stress"
        indicator = "NDMI"
    elif layer == "truecolor":
        health_color = "#64748b"
        health_text = "Satellite"
        indicator = "TRUE COLOR"
    else:
        health_color = "#4ade80" if ndvi > 0.6 else "#fbbf24" if ndvi > 0.3 else "#f87171"
        health_text = "Healthy" if ndvi > 0.6 else "Moderate" if ndvi > 0.3 else "Stressed"
        indicator = "NDVI"

    gradient_start = "#1a1a2e" if ndvi > 0.5 else "#2d1f1f"
    gradient_end = "#16213e" if ndvi > 0.5 else "#1a0a0a"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{gradient_start};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{gradient_end};stop-opacity:1" />
    </linearGradient>
    <linearGradient id="vg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{health_color};stop-opacity:0.15" />
      <stop offset="100%" style="stop-color:{health_color};stop-opacity:0.05" />
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#bgGrad)" />
  <rect x="24" y="24" width="464" height="464" fill="none" stroke="{health_color}" stroke-width="1" stroke-dasharray="8,4" opacity="0.3" />
  <rect x="64" y="100" width="384" height="312" rx="4" fill="url(#vg)" />
  <g fill="{health_color}" opacity="0.2">
    <ellipse cx="128" cy="180" rx="40" ry="25" /><ellipse cx="256" cy="160" rx="50" ry="30" />
    <ellipse cx="384" cy="180" rx="40" ry="25" /><ellipse cx="170" cy="280" rx="45" ry="28" />
    <ellipse cx="300" cy="260" rx="35" ry="22" /><ellipse cx="256" cy="340" rx="60" ry="35" />
  </g>
  <text x="256" y="440" font-family="monospace" font-size="14" fill="{health_color}" text-anchor="middle" font-weight="bold">{indicator}: {ndvi:.3f}</text>
  <text x="256" y="465" font-family="monospace" font-size="12" fill="#94a3b8" text-anchor="middle">{health_text}</text>
  <text x="256" y="485" font-family="monospace" font-size="10" fill="#64748b" text-anchor="middle">{lat:.4f}, {lon:.4f}</text>
</svg>"""
    return svg.encode("utf-8")


def _decode_data_uri_image(data_uri: str) -> tuple[bytes, str]:
    header, encoded = data_uri.split(",", 1)
    mime_type = header.split(";")[0].replace("data:", "")
    return base64.b64decode(encoded), mime_type


async def _get_satellite_image_base64(lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
    token = await _get_sentinel_token()

    evalscript = NDVI_EVALSCRIPT
    if layer == "ndmi":
        evalscript = NDMI_EVALSCRIPT
    elif layer == "truecolor":
        evalscript = TRUE_COLOR_EVALSCRIPT

    if token:
        image_bytes = await _fetch_sentinel_image(token, lat, lon, evalscript)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            return f"data:image/png;base64,{b64}"
        logger.warning("Sentinel image fetch returned no data, using placeholder")

    svg_bytes = _generate_placeholder_svg(lat, lon, ndvi, layer)
    return f"data:image/svg+xml;base64,{base64.b64encode(svg_bytes).decode()}"


def _build_history_point(lat: float, lon: float, offset_months: int, now: datetime) -> dict[str, Any]:
    target_date = now - timedelta(days=30 * offset_months)
    seed = int(abs(lat * lon * 1000000 + offset_months * 1000) % 10000)
    base_ndvi = 0.55 + (seed / 100000) - 0.05

    month = target_date.month
    if month in [3, 4, 5]:
        seasonal_adjustment = 0.1
    elif month in [11, 12, 1, 2]:
        seasonal_adjustment = -0.15
    else:
        seasonal_adjustment = 0.0

    ndvi_value = max(0.1, min(0.9, base_ndvi + seasonal_adjustment))
    return {
        "date": target_date.strftime("%Y-%m"),
        "ndvi": round(ndvi_value, 3),
        "status": "healthy" if ndvi_value > 0.6 else "moderate" if ndvi_value > 0.4 else "stressed",
    }


def _enrich_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for idx, point in enumerate(history):
        if idx == 0:
            point["monthly_change"] = None
        else:
            point["monthly_change"] = round(point["ndvi"] - history[idx - 1]["ndvi"], 3)

        window = history[max(0, idx - 2): idx + 1]
        point["moving_avg_3m"] = round(sum(item["ndvi"] for item in window) / len(window), 3)
    return history


def _build_ndvi_history(lat: float, lon: float, months: int, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    raw_history = [
        _build_history_point(lat, lon, i, now)
        for i in range(min(months, 24))
    ]
    raw_history.reverse()
    return _enrich_history(raw_history)


def _evaluate_alerts(history: list[dict[str, Any]], reference_date: str | None = None) -> list[dict[str, Any]]:
    if not history:
        return []

    current = history[-1]
    alerts: list[dict[str, Any]] = []
    triggered_at = reference_date or current["date"]

    if len(history) >= 3:
        baseline = history[-3]["ndvi"]
        change_2m = round(current["ndvi"] - baseline, 3)
        if change_2m <= -0.12:
            alerts.append({
                "rule_id": "drop_2m_gt_0_12",
                "severity": "high",
                "title": "Caída abrupta de vigor",
                "probable_cause": "Estrés hídrico o evento climático reciente.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": baseline,
                    "change": change_2m,
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    if current["ndvi"] < 0.35:
        alerts.append({
            "rule_id": "critical_low_ndvi",
            "severity": "high",
            "title": "NDVI críticamente bajo",
            "probable_cause": "Daño foliar, plaga o estrés hídrico severo.",
            "triggered_at": triggered_at,
            "evidence": {
                "current_ndvi": current["ndvi"],
                "baseline_ndvi": None,
                "change": None,
                "moving_avg_3m": current.get("moving_avg_3m"),
            },
        })

    if len(history) >= 4:
        last_changes = [point.get("monthly_change", 0) for point in history[-3:]]
        total_change = round(sum(last_changes), 3)
        if all(change is not None and change < 0 for change in last_changes) and total_change <= -0.15:
            alerts.append({
                "rule_id": "persistent_decline_3m",
                "severity": "medium",
                "title": "Deterioro sostenido",
                "probable_cause": "Problemas de manejo agronómico o déficit hídrico acumulado.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": history[-4]["ndvi"],
                    "change": total_change,
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    if len(history) >= 6:
        recent = [point["ndvi"] for point in history[-6:]]
        volatility = statistics.pstdev(recent)
        if volatility >= 0.1:
            alerts.append({
                "rule_id": "high_ndvi_volatility",
                "severity": "low",
                "title": "Alta volatilidad de NDVI",
                "probable_cause": "Variabilidad fenológica o heterogeneidad del lote.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": round(sum(recent) / len(recent), 3),
                    "change": round(volatility, 3),
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda alert: severity_order.get(alert["severity"], 3))
    return alerts


def _build_alert_evidence(alerts: list[dict[str, Any]], ndvi: float) -> dict[str, Any]:
    if not alerts:
        return {"has_alerts": False, "ndvi": round(ndvi, 3)}

    return {
        "has_alerts": True,
        "alert_count": len(alerts),
        "highest_severity": alerts[0]["severity"],
        "rules": [alert["rule_id"] for alert in alerts],
        "ndvi": round(ndvi, 3),
    }
