#!/usr/bin/env python3
"""Génère les cartes synoptiques AROME-PI avec Matplotlib et Cartopy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import cartopy.crs as ccrs
from cartopy.io import shapereader
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap
import matplotlib.patheffects as path_effects
import numpy as np
from scipy.ndimage import gaussian_filter
from shapely.geometry import shape


# L'emprise source reste celle du raster AROME Europe de l'Ouest. Seule la
# fenêtre affichée est resserrée sur la France métropolitaine, avec la Corse
# entière et une petite marge permettant de lire les systèmes entrants.
FRANCE_DISPLAY_EXTENT = (-6.5, 10.5, 41.0, 52.0)
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

# Villes de repère, volontairement limitées aux principaux centres pour garder
# une carte lisible. Les décalages évitent que le libellé masque le point.
FRANCE_CITIES = (
    ("Brest", 48.3904, -4.4861, 5, 4),
    ("Rennes", 48.1173, -1.6778, 5, 4),
    ("Nantes", 47.2184, -1.5536, 5, -9),
    ("Caen", 49.1829, -0.3707, 5, 4),
    ("Rouen", 49.4432, 1.0993, 5, 4),
    ("Lille", 50.6292, 3.0573, 5, 4),
    ("Amiens", 49.8941, 2.2957, -5, -9),
    ("Paris", 48.8566, 2.3522, 5, 4),
    ("Reims", 49.2583, 4.0317, 5, 4),
    ("Metz", 49.1193, 6.1757, 5, 4),
    ("Strasbourg", 48.5734, 7.7521, 5, 4),
    ("Orléans", 47.9030, 1.9093, 5, 4),
    ("Tours", 47.3941, 0.6848, 5, -9),
    ("Dijon", 47.3220, 5.0415, 5, 4),
    ("Besançon", 47.2378, 6.0241, 5, -9),
    ("Poitiers", 46.5802, 0.3404, 5, 4),
    ("La Rochelle", 46.1603, -1.1511, 5, -9),
    ("Limoges", 45.8336, 1.2611, 5, 4),
    ("Clermont-Fd", 45.7772, 3.0870, 5, -9),
    ("Lyon", 45.7640, 4.8357, 5, 4),
    ("Grenoble", 45.1885, 5.7245, 5, -9),
    ("Bordeaux", 44.8378, -0.5792, 5, 4),
    ("Pau", 43.2951, -0.3708, 5, 4),
    ("Toulouse", 43.6047, 1.4442, 5, 4),
    ("Perpignan", 42.6887, 2.8948, 5, 4),
    ("Montpellier", 43.6108, 3.8767, 5, -9),
    ("Marseille", 43.2965, 5.3698, 5, 4),
    ("Nice", 43.7102, 7.2620, 5, 4),
    ("Ajaccio", 41.9192, 8.7386, 5, 4),
    ("Bastia", 42.6973, 9.4509, 5, 4),
)


@dataclass(frozen=True)
class SynopticSpec:
    key: str
    label: str
    group: str
    field: str
    unit: str
    levels: tuple[float, ...]
    colours: tuple[str, ...]
    extend: str = "both"
    smoothing_sigma: float = 1.8
    map_layer: str = ""


SYNOPTIC_SPECS = (
    SynopticSpec(
        "temperature_2m",
        "Température à 2 m",
        "Température",
        "temperature_c",
        "°C",
        tuple(range(-24, 39, 2)),
        (
            "#25104f", "#34339a", "#2468bd", "#21a6cf", "#39c8b3",
            "#76d36c", "#c7df3e", "#ffe22d", "#ffad27", "#ff6c22",
            "#e52d2f", "#981d54", "#50113e",
        ),
        smoothing_sigma=1.15,
        map_layer="temperature",
    ),
    SynopticSpec(
        "point_rosee",
        "Point de rosée à 2 m",
        "Température",
        "dewpoint_c",
        "°C",
        tuple(range(-24, 31, 3)),
        (
            "#3d1766", "#38459c", "#2f79b7", "#3ba7c5", "#51c5a8",
            "#79d06e", "#c9dc48", "#f1cf3f", "#eda13a", "#df653b",
            "#b6314c", "#711d53",
        ),
        smoothing_sigma=1.1,
        map_layer="point_rosee",
    ),
    SynopticSpec(
        "precipitations_1h",
        "Précipitations sur 1 h",
        "Précipitations",
        "precipitation_mm",
        "mm",
        (0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60),
        (
            "#d8efff", "#8bc8ff", "#3f91ff", "#16d5e5", "#04b686",
            "#65dd38", "#d8e92d", "#ffe62a", "#ffc12b", "#ff8624",
            "#f04432", "#c11c75", "#6d1ca5",
        ),
        "max",
        0.65,
        "pluie_1h",
    ),
    SynopticSpec(
        "cumul_precipitations",
        "Cumul des précipitations",
        "Précipitations",
        "precipitation_total_mm",
        "mm",
        (0.1, 1, 2, 5, 10, 15, 20, 30, 40, 60, 100, 150, 250),
        (
            "#e8f4ff", "#9ed2ff", "#559eff", "#1fd1df", "#16b77e",
            "#79d839", "#e4e62f", "#ffd52b", "#ffa329", "#f35c2b",
            "#d32c61", "#8a239b", "#431978",
        ),
        "max",
        0.65,
        "pluie_cumul",
    ),
    SynopticSpec(
        "cumul_neige",
        "Cumul neige",
        "Neige",
        "snowfall_total_mm",
        "mm",
        (0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50),
        (
            "#f7fbff", "#dbefff", "#aedcff", "#75bff2", "#4d9bdc",
            "#526fc4", "#6d53b5", "#8c429e", "#b24c96", "#d76c9f",
            "#ed9fc0", "#f6d7e9",
        ),
        "max",
        0.65,
        "equivalent_eau_neige",
    ),
    SynopticSpec(
        "cumul_neige_graupel",
        "Cumul neige + graupel",
        "Neige",
        "snow_graupel_total_mm",
        "mm",
        (0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50),
        (
            "#f9fbff", "#d6eeff", "#9bdcff", "#53c6e6", "#3aa8c8",
            "#4381bd", "#625bb4", "#873fa4", "#b33e91", "#da557d",
            "#ef8aa3", "#f5c9df",
        ),
        "max",
        0.65,
        "neige_graupel",
    ),
    SynopticSpec(
        "vent_10m",
        "Vent à 10 m",
        "Vent",
        "wind_speed_kmh",
        "km/h",
        (0, 10, 20, 30, 40, 50, 60, 80, 100, 120, 150),
        (
            "#eef7e8", "#b8e186", "#6fcd70", "#3db8a0", "#398dcc",
            "#545fc0", "#8248ad", "#b63d82", "#dd3c55", "#9d243f",
            "#4b172d",
        ),
        "max",
        0.9,
        "vent",
    ),
    SynopticSpec(
        "rafales_10m",
        "Rafales à 10 m",
        "Vent",
        "wind_gust_kmh",
        "km/h",
        (0, 20, 30, 40, 50, 60, 70, 80, 100, 120, 140, 170),
        (
            "#eef7e8", "#b8e186", "#6fcd70", "#3db8a0", "#398dcc",
            "#545fc0", "#8248ad", "#b63d82", "#dd3c55", "#bc263f",
            "#781b3b", "#351426",
        ),
        "max",
        0.85,
        "rafales",
    ),
    SynopticSpec(
        "rafales_max_10m",
        "Rafales maximales à 10 m",
        "Vent",
        "wind_gust_max_kmh",
        "km/h",
        (0, 20, 30, 40, 50, 60, 70, 80, 100, 120, 140, 170),
        (
            "#eef7e8", "#b8e186", "#6fcd70", "#3db8a0", "#398dcc",
            "#545fc0", "#8248ad", "#b63d82", "#dd3c55", "#bc263f",
            "#781b3b", "#351426",
        ),
        "max",
        0.85,
        "rafales_max_10m",
    ),
    SynopticSpec(
        "humidite_relative",
        "Humidité relative",
        "Nuages et humidité",
        "humidity_pct",
        "%",
        tuple(range(0, 110, 10)),
        (
            "#8b3f26", "#bb6934", "#df9a42", "#ebc85a", "#d8df75",
            "#a8d77b", "#69c58c", "#39ada3", "#3287b5", "#405f9f",
            "#3d376e",
        ),
        "neither",
        1.0,
        "humidite",
    ),
    SynopticSpec(
        "sbcape",
        "SBCAPE",
        "Instabilité",
        "cape_jkg",
        "J/kg",
        (0, 100, 300, 500, 800, 1200, 1800, 2500, 3500, 5000),
        (
            "#f3f5f8", "#d8ebff", "#91c8ff", "#41a8df", "#31c878",
            "#d5e52f", "#ffc62d", "#ff7a22", "#e83028", "#8c1d74",
        ),
        "max",
        0.6,
        "mucape",
    ),
    SynopticSpec(
        "iso_zero",
        "Altitude de l’isotherme 0 °C",
        "Pression et altitude",
        "freezing_level_m",
        "m",
        tuple(range(0, 5500, 500)),
        (
            "#4b1d70", "#384fa7", "#318bc2", "#3dbdb2", "#75cf72",
            "#d9dc43", "#f3ae36", "#e76e34", "#c9364b", "#721b64",
            "#3b143f",
        ),
        smoothing_sigma=1.0,
        map_layer="iso_zero",
    ),
)


class SynopticMapRenderer:
    """Produit des PNG autonomes, avec titres, isolignes et fond Cartopy."""

    def __init__(
        self,
        output_directory: Path,
        *,
        width: int,
        height: int,
        bounds: dict[str, float],
        boundary_directory: Path,
    ) -> None:
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.width = int(width)
        self.height = int(height)
        self.bounds = dict(bounds)
        self.boundary_directory = Path(boundary_directory)
        self.steps: list[dict[str, Any]] = []
        self.available_layers: set[str] = set()

        north = float(self.bounds["north"])
        south = float(self.bounds["south"])
        north_y = np.log(np.tan(np.pi / 4 + np.radians(north) / 2))
        south_y = np.log(np.tan(np.pi / 4 + np.radians(south) / 2))
        mercator_rows = np.linspace(north_y, south_y, self.height)
        self.latitudes = np.degrees(2 * np.arctan(np.exp(mercator_rows)) - np.pi / 2)
        self.longitudes = np.linspace(
            float(self.bounds["west"]), float(self.bounds["east"]), self.width
        )

    def _add_boundaries(self, axis) -> None:
        departments_path = self.boundary_directory / "departements-100m.geojson"
        if not departments_path.is_file():
            departments_path = self.boundary_directory / "departements-1000m.geojson"
        if departments_path.is_file():
            with departments_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            geometries = [
                shape(feature["geometry"])
                for feature in payload.get("features", [])
                if str(feature.get("properties", {}).get("code", ""))
                in {
                    f"{number:02d}" for number in range(1, 96)
                } | {"2A", "2B"}
            ]
            axis.add_geometries(
                geometries,
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor="#343a40",
                linewidth=0.62,
                alpha=0.88,
                zorder=7,
            )
        for filename, colour, linewidth in (
            ("ne_50m_admin_0_boundary_lines_land.shp", "#5f6670", 0.55),
            ("ne_50m_coastline.shp", "#30343a", 0.8),
        ):
            path = self.boundary_directory / filename
            if path.is_file():
                axis.add_geometries(
                    shapereader.Reader(path).geometries(),
                    crs=ccrs.PlateCarree(),
                    facecolor="none",
                    edgecolor=colour,
                    linewidth=linewidth,
                    zorder=8,
                )

    @staticmethod
    def _add_cities(axis) -> None:
        transform = ccrs.PlateCarree()
        halo = [path_effects.withStroke(linewidth=2.1, foreground="#ffffff")]
        for name, latitude, longitude, offset_x, offset_y in FRANCE_CITIES:
            axis.plot(
                longitude,
                latitude,
                marker="o",
                markersize=2.7,
                markerfacecolor="#111111",
                markeredgecolor="#ffffff",
                markeredgewidth=0.55,
                transform=transform,
                zorder=10,
            )
            axis.annotate(
                name,
                xy=(longitude, latitude),
                xytext=(offset_x, offset_y),
                textcoords="offset points",
                color="#151515",
                fontsize=6.3,
                fontweight="bold",
                path_effects=halo,
                transform=transform,
                zorder=11,
            )

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat().replace("+00:00", "Z") if value else None

    @staticmethod
    def _smooth(values: np.ndarray, sigma: float) -> np.ndarray:
        """Lisse un champ sans faire déborder les zones manquantes."""
        source = np.asarray(values, dtype=np.float64)
        finite = np.isfinite(source)
        if not np.any(finite) or sigma <= 0:
            return source
        weights = gaussian_filter(
            finite.astype(np.float64), sigma=sigma, mode="nearest"
        )
        smoothed = gaussian_filter(
            np.where(finite, source, 0.0), sigma=sigma, mode="nearest"
        )
        result = np.full(source.shape, np.nan, dtype=np.float64)
        np.divide(smoothed, weights, out=result, where=weights > 1.0e-6)
        return result

    def _render_one(
        self,
        spec: SynopticSpec,
        field: np.ndarray,
        *,
        lead_hour: int,
        run_time: datetime | None,
        valid_time: datetime,
        destination: Path,
    ) -> None:
        stride = max(1, int(max(self.width, self.height) / 720))
        values = np.asarray(field, dtype=np.float64)[::stride, ::stride]
        values = self._smooth(values, spec.smoothing_sigma)
        longitudes = self.longitudes[::stride]
        latitudes = self.latitudes[::stride]
        longitude_grid, latitude_grid = np.meshgrid(longitudes, latitudes)
        masked = np.ma.masked_invalid(values)

        cmap = LinearSegmentedColormap.from_list(
            f"ampi_{spec.key}", spec.colours, N=max(256, len(spec.levels) * 16)
        )
        norm = BoundaryNorm(spec.levels, cmap.N, extend=spec.extend)
        fig = plt.figure(figsize=(16, 12), dpi=200, facecolor="white")
        projection = ccrs.LambertConformal(
            central_longitude=2.0,
            central_latitude=46.5,
            standard_parallels=(44.0, 49.0),
        )
        axis = fig.add_axes((0.035, 0.075, 0.855, 0.84), projection=projection)
        axis.set_extent(FRANCE_DISPLAY_EXTENT, crs=ccrs.PlateCarree())
        filled = axis.contourf(
            longitude_grid,
            latitude_grid,
            masked,
            levels=spec.levels,
            cmap=cmap,
            norm=norm,
            extend=spec.extend,
            transform=ccrs.PlateCarree(),
            antialiased=True,
            zorder=1,
        )
        field_span = float(np.nanmax(values) - np.nanmin(values))
        if np.isfinite(field_span) and field_span > 0:
            contour_levels = np.asarray(spec.levels[::2], dtype=np.float64)
            contour_levels = contour_levels[
                (contour_levels > np.nanmin(values))
                & (contour_levels < np.nanmax(values))
            ]
            if contour_levels.size < 2:
                contour_levels = min(8, max(4, int(field_span / 4)))
            contours = axis.contour(
                longitude_grid,
                latitude_grid,
                masked,
                levels=contour_levels,
                colors="#111111",
                linewidths=0.6,
                alpha=0.78,
                transform=ccrs.PlateCarree(),
                zorder=5,
            )
            axis.clabel(contours, inline=True, fontsize=6, fmt="%g")

        self._add_boundaries(axis)
        self._add_cities(axis)
        axis.set_xticks([])
        axis.set_yticks([])

        run_label = (
            run_time.astimezone(PARIS_TIMEZONE).strftime("%d/%m/%Y %Hh")
            if run_time else "indisponible"
        )
        valid_label = valid_time.astimezone(PARIS_TIMEZONE).strftime("%a %d/%m %Hh")
        fig.text(
            0.5,
            0.955,
            f"{spec.label}  |  Run {run_label}  —  Échéance +{lead_hour:03d} h  —  Validité {valid_label}",
            ha="center",
            va="center",
            fontsize=13,
            color="#111111",
        )
        colour_axis = fig.add_axes((0.91, 0.18, 0.022, 0.65))
        colourbar = fig.colorbar(
            filled,
            cax=colour_axis,
            orientation="vertical",
            ticks=spec.levels if spec.key == "temperature_2m" else None,
        )
        colourbar.set_label(f"{spec.label} ({spec.unit})", fontsize=10)
        colourbar.ax.tick_params(labelsize=6 if spec.key == "temperature_2m" else 8)
        fig.text(
            0.5,
            0.028,
            "www.alertes-meteo.com",
            ha="center",
            va="center",
            fontsize=6,
            color="#555555",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(destination, format="png", facecolor="white", bbox_inches=None)
        plt.close(fig)

    def render_step(
        self,
        *,
        lead_hour: int,
        run_time: datetime | None,
        valid_time: datetime,
        fields: dict[str, np.ndarray],
    ) -> None:
        files: dict[str, str] = {}
        for spec in SYNOPTIC_SPECS:
            field = fields.get(spec.field)
            if field is None or not np.any(np.isfinite(field)):
                continue
            destination = self.output_directory / spec.key / f"{lead_hour:03d}.png"
            self._render_one(
                spec,
                field,
                lead_hour=lead_hour,
                run_time=run_time,
                valid_time=valid_time,
                destination=destination,
            )
            files[spec.key] = f"synoptic/{spec.key}/{destination.name}"
            self.available_layers.add(spec.key)
        self.steps.append(
            {
                "lead_hour": int(lead_hour),
                "valid_time": self._iso(valid_time),
                "files": files,
            }
        )

    def write_manifest(self, *, generated_at: str, run_time: str | None) -> dict[str, Any]:
        manifest = {
            "schema_version": 1,
            "status": "ok",
            "generator": "Matplotlib + Cartopy",
            "generated_at": generated_at,
            "run_time": run_time,
            "layers": {
                spec.key: {
                    "label": spec.label,
                    "group": spec.group,
                    "unit": spec.unit,
                    "map_layer": spec.map_layer,
                    "stops": [
                        {
                            "value": value,
                            "color": matplotlib.colors.to_hex(
                                LinearSegmentedColormap.from_list(
                                    f"manifest_{spec.key}", spec.colours
                                )(index / max(1, len(spec.levels) - 1))
                            ),
                        }
                        for index, value in enumerate(spec.levels)
                    ],
                }
                for spec in SYNOPTIC_SPECS
                if spec.key in self.available_layers
            },
            "steps": self.steps,
        }
        with (self.output_directory / "index.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        return manifest
