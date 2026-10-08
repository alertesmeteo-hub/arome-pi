"""PIAF (Prévision Immédiate Agrégée Fusionnée) : lame d'eau 5 min jusqu'à +3 h, Météo-France.

L'API ciblée WCS « PrevisionImmediatePrecipitations » (contexte api.meteofrance.fr/pro/piaf/1.0) sert
un champ de précipitations par échéance (pas de 5 min, 36 échéances). On ne télécharge que le découpage
Pyrénées-Orientales et on publie, au même format que les autres modèles, le fichier departements/66.json
(points de grille AROME-PI du département, pluie par pas de 5 min et cumul depuis le run).

Clé : METEOFRANCE_PIAF_KEY (clé d'application régénérée après souscription à l'API), sinon METEOFRANCE_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests

BASE = "https://api.meteofrance.fr/pro/piaf/1.0/wcs/MF-NWP-HIGHRES-PIAF-001-FRANCE-WCS/"
UA = "Mozilla/5.0 (compatible; AlertesMeteo-PIAF/1.0)"
LAT0, LAT1, LON0, LON1 = 41.9, 43.3, 1.4, 3.5
POINTS_URL = "https://raw.githubusercontent.com/alertesmeteo-hub/arome-pi/data/departements/66.json"
MIN_INTERVAL = 1.5
MIN_LEADS = 12  # au moins 1 h d'échéances pour publier
_last_call = 0.0


def call(session: requests.Session, query: str, key: str) -> requests.Response:
    """Un appel WCS espacé de MIN_INTERVAL, avec reprise sur 429/5xx."""
    global _last_call
    for attempt in range(6):
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        r = session.get(BASE + query, headers={"apikey": key, "User-Agent": UA}, timeout=(15, 120))
        if r.status_code in (429, 500, 502, 503, 504):
            delay = min(120, 15 * 2**attempt)
            try:
                delay = max(delay, int(r.headers.get("Retry-After", "0")))
            except ValueError:
                pass
            print(f"HTTP {r.status_code} ({query[:40]}…), reprise dans {delay} s", flush=True)
            time.sleep(delay)
            continue
        return r
    return r


def latest_coverage(session: requests.Session, key: str) -> tuple[str, str]:
    """Identifiant de la couverture précipitations la plus récente et son réseau (ISO)."""
    r = call(session, "GetCapabilities?service=WCS&version=2.0.1&language=eng", key)
    if r.status_code != 200:
        raise RuntimeError(f"GetCapabilities HTTP {r.status_code} : {r.text[:200]}")
    ids = re.findall(r"<wcs:CoverageId>([^<]+)</wcs:CoverageId>", r.text)
    print("Couvertures :", ", ".join(sorted(set(i.split("___")[0] for i in ids))) or "aucune", flush=True)
    rain = [i for i in ids if "PRECIP" in i.upper() or "RAIN" in i.upper()]
    if not rain:
        raise RuntimeError("Aucune couverture de précipitations dans le catalogue PIAF")

    def stamp(i: str) -> str:
        m = re.search(r"___(\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2}Z)", i)
        return m.group(1) if m else ""

    # réseau le plus récent ; à réseau égal, on préfère la lame d'eau 5 min (suffixe _PT5M) puis l'id le plus court
    rain.sort(key=lambda i: (stamp(i), "PT5M" in i, -len(i)), reverse=True)
    cid = rain[0]
    run_iso = stamp(cid).replace(".", ":")
    return cid, run_iso


def lead_seconds(session: requests.Session, key: str, cid: str) -> list[int]:
    r = call(session, f"DescribeCoverage?service=WCS&version=2.0.1&coverageid={cid}", key)
    if r.status_code != 200:
        raise RuntimeError(f"DescribeCoverage HTTP {r.status_code} : {r.text[:200]}")
    best: list[int] = []
    for block in re.findall(r"<gmlrgrid:coefficients>([^<]+)</gmlrgrid:coefficients>", r.text):
        vals = []
        for tok in block.split():
            try:
                vals.append(int(float(tok)))
            except ValueError:
                vals = []
                break
        # l'axe temps : plusieurs valeurs en secondes, toutes ≥ 60
        if len(vals) > len(best) and vals and min(vals) >= 60:
            best = vals
    if not best:
        raise RuntimeError("Axe temps introuvable dans DescribeCoverage")
    return sorted(set(best))


def decode(content: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Grille (lignes = latitudes, colonnes = longitudes) et axes lat/lon en degrés."""
    from eccodes import codes_get, codes_get_values, codes_new_from_message, codes_release

    handle = codes_new_from_message(content)
    try:
        ni, nj = codes_get(handle, "Ni"), codes_get(handle, "Nj")
        lat0 = codes_get(handle, "latitudeOfFirstGridPointInDegrees")
        lon0 = codes_get(handle, "longitudeOfFirstGridPointInDegrees")
        di = codes_get(handle, "iDirectionIncrementInDegrees")
        dj = codes_get(handle, "jDirectionIncrementInDegrees")
        jpos = codes_get(handle, "jScansPositively")
        values = np.asarray(codes_get_values(handle), dtype=float).reshape(nj, ni)
        lats = lat0 + (np.arange(nj) * dj if jpos else -np.arange(nj) * dj)
        lons = lon0 + np.arange(ni) * di
        lons = np.where(lons > 180, lons - 360, lons)
        return values, lats, lons
    finally:
        codes_release(handle)


def already_published(url: str, run_iso: str) -> bool:
    try:
        r = requests.get(url, timeout=(10, 30), headers={"User-Agent": UA})
        return r.status_code == 200 and r.json().get("model", {}).get("run_time") == run_iso
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="build/piaf")
    parser.add_argument("--current-index-url", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    key = (os.environ.get("METEOFRANCE_PIAF_KEY") or os.environ.get("METEOFRANCE_API_KEY") or "").strip()
    if not key:
        print("Clé Météo-France absente (METEOFRANCE_PIAF_KEY ou METEOFRANCE_API_KEY)", file=sys.stderr)
        return 1

    session = requests.Session()
    cid, run_iso = latest_coverage(session, key)
    print("Couverture retenue :", cid, "— run", run_iso, flush=True)
    if not args.force and args.current_index_url and already_published(args.current_index_url, run_iso):
        print(f"Run {run_iso} déjà publié.")
        return 0
    run_dt = datetime.fromisoformat(run_iso.replace("Z", "+00:00"))
    leads = lead_seconds(session, key, cid)
    print(f"{len(leads)} échéances, de +{leads[0]//60} à +{leads[-1]//60} min", flush=True)

    src = requests.get(POINTS_URL, timeout=(10, 60), headers={"User-Agent": UA}).json()
    points = src["points"]  # [id, lat, lon, alt]
    plat = np.array([p[1] for p in points], dtype=float)
    plon = np.array([p[2] for p in points], dtype=float)

    steps: list[tuple[datetime, np.ndarray]] = []
    for lead in leads:
        valid = run_dt + timedelta(seconds=lead)
        stamp = valid.strftime("%Y-%m-%dT%H:%M:%SZ")
        q = (
            f"GetCoverage?service=WCS&version=2.0.1&coverageid={cid}&format=application%2Fwmo-grib"
            f"&subset=time({stamp})&subset=lat({LAT0},{LAT1})&subset=long({LON0},{LON1})"
        )
        r = call(session, q, key)
        if r.status_code != 200 or r.content[:4] != b"GRIB":
            print(f"+{lead//60} min : HTTP {r.status_code}, ignoré ({r.text[:120] if r.status_code != 200 else 'pas un GRIB'})", flush=True)
            continue
        grid, lats, lons = decode(r.content)
        grid = np.nan_to_num(grid, nan=0.0)
        grid[grid < 0] = 0
        # plus proche maille pour chaque point du département
        ri = np.clip(np.rint((plat - lats[0]) / (lats[1] - lats[0])).astype(int), 0, len(lats) - 1)
        ci = np.clip(np.rint((plon - lons[0]) / (lons[1] - lons[0])).astype(int), 0, len(lons) - 1)
        steps.append((valid, grid[ri, ci]))
        if len(steps) % 6 == 0:
            print(f"  {len(steps)} échéances lues, maxi {float(grid.max()):.1f} mm/5 min", flush=True)

    if len(steps) < MIN_LEADS:
        print(f"Seulement {len(steps)} échéances exploitables (< {MIN_LEADS}) : pas de publication", file=sys.stderr)
        return 1

    out = Path(args.output_dir)
    (out / "departements").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    forecast = []
    total = np.zeros(len(points))
    for valid, vals in steps:
        total = total + vals
        rows = [[round(float(v), 2), round(float(t), 2)] for v, t in zip(vals, total)]
        forecast.append([valid.strftime("%Y-%m-%dT%H:%M:%SZ"), rows])
    dep = {
        "schema_version": 3,
        "status": "ok",
        "generated_at": now,
        "department": "66",
        "columns": {"values": ["precipitation_mm", "precipitation_total_mm"], "communes": src["columns"]["communes"]},
        "points": points,
        "communes": src["communes"],
        "forecast": forecast,
    }
    (out / "departements" / "66.json").write_text(json.dumps(dep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = {
        "schema_version": 3,
        "status": "ok",
        "generated_at": now,
        "model": {
            "name": "PIAF 1 km — pluie 5 min (Météo-France)",
            "provider": "Météo-France",
            "resolution_km": 1.0,
            "forecast_hours_requested": 3,
            "step_minutes": 5,
            "run_time": run_iso,
            "coverage_id": cid,
            "source_url": "https://portail-api.meteofrance.fr/web/fr/api/PrevisionImmediatePrecipitations",
            "license": "Licence Ouverte 2.0",
        },
        "departments": {"66": {"file": "departements/66.json", "points": len(points), "steps": len(forecast)}},
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    cumul_max = float(total.max())
    print(f"PIAF {run_iso} : {len(forecast)} échéances, {len(points)} points, cumul maxi {cumul_max:.1f} mm sur {len(forecast)*5} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
