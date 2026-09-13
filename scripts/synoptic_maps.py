#!/usr/bin/env python3
"""Génère les cartes synoptiques AROME-PI avec Matplotlib et Cartopy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import cartopy.crs as ccrs
from cartopy.io import shapereader
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap
import numpy as np
from scipy.ndimage import gaussian_filter


# L'emprise source reste celle du raster AROME Europe de l'Ouest. Seule la
# fenêtre affichée est resserrée sur la France métropolitaine, avec la Corse
# entière et une petite marge permettant de lire les systèmes entrants.
FRANCE_DISPLAY_EXTENT = (-6.5, 10.5, 41.0, 52.0)


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


SYNOPTIC_SPECS = (
    SynopticSpec(
        "temperature_pression",
        "Température à 2 m / pression",
        "Température",
        "temperature_c",
        "°C",
        tuple(range(-24, 37, 3)),
        (
            "#25104f", "#34339a", "#2468bd", "#21a6cf", "#39c8b3",
            "#76d36c", "#c7df3e", "#ffe22d", "#ffad27", "#ff6c22",
            "#e52d2f", "#981d54", "#50113e",
        ),
        smoothing_sigma=2.2,
    ),
    SynopticSpec(
        "precipitations_pression",
        "Précipitations sur 1 h / pression",
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
        1.0,
    ),
    SynopticSpec(
        "rafales_pression",
        "Rafales à 10 m / pression",
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
        1.2,
    ),
    SynopticSpec(
        "humidite_pression",
        "Humidité relative / pression",
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
        1.8,
    ),
    SynopticSpec(
        "sbcape_pression",
        "SBCAPE / pression",
        "Instabilité",
        "cape_jkg",
        "J/kg",
        (0, 100, 300, 500, 800, 1200, 1800, 2500, 3500, 5000),
        (
            "#f3f5f8", "#d8ebff", "#91c8ff", "#41a8df", "#31c878",
            "#d5e52f", "#ffc62d", "#ff7a22", "#e83028", "#8c1d74",
        ),
        "max",
        0.9,
    ),
    SynopticSpec(
        "iso_zero_pression",
        "Isotherme 0 °C / pression",
        "Pression et altitude",
        "freezing_level_m",
        "m",
        tuple(range(0, 5500, 500)),
        (
            "#4b1d70", "#384fa7", "#318bc2", "#3dbdb2", "#75cf72",
            "#d9dc43", "#f3ae36", "#e76e34", "#c9364b", "#721b64",
            "#3b143f",
        ),
        smoothing_sigma=2.0,
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
        pressure: np.ndarray | None,
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
        fig = plt.figure(figsize=(15.5, 11.6), dpi=140, facecolor="white")
        axis = fig.add_axes((0.035, 0.075, 0.855, 0.84), projection=ccrs.PlateCarree())
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

        if pressure is not None and np.any(np.isfinite(pressure)):
            pressure_values = np.asarray(pressure, dtype=np.float64)[::stride, ::stride]
            pressure_values = self._smooth(pressure_values, 2.4)
            pressure_masked = np.ma.masked_invalid(pressure_values)
            pressure_min = max(900, 5 * np.ceil(np.nanmin(pressure_values) / 5))
            pressure_max = min(1080, 5 * np.floor(np.nanmax(pressure_values) / 5))
            if pressure_max > pressure_min:
                pressure_contours = axis.contour(
                    longitude_grid,
                    latitude_grid,
                    pressure_masked,
                    levels=np.arange(pressure_min, pressure_max + 1, 5),
                    colors="white",
                    linewidths=1.35,
                    transform=ccrs.PlateCarree(),
                    zorder=6,
                )
                axis.clabel(
                    pressure_contours,
                    inline=True,
                    fontsize=7,
                    colors="white",
                    fmt="%d",
                )

        self._add_boundaries(axis)
        axis.set_xticks([])
        axis.set_yticks([])

        run_label = run_time.strftime("%d/%m/%Y %HZ") if run_time else "indisponible"
        valid_label = valid_time.strftime("%a %d/%m %HZ")
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
        colourbar = fig.colorbar(filled, cax=colour_axis, orientation="vertical")
        colourbar.set_label(f"{spec.label} ({spec.unit})", fontsize=10)
        colourbar.ax.tick_params(labelsize=8)
        fig.text(
            0.5,
            0.028,
            "www.alertes-meteo.com",
            ha="center",
            va="center",
            fontsize=10,
            color="#666666",
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
        pressure = fields.get("pressure_hpa")
        for spec in SYNOPTIC_SPECS:
            field = fields.get(spec.field)
            if field is None or not np.any(np.isfinite(field)):
                continue
            destination = self.output_directory / spec.key / f"{lead_hour:03d}.png"
            self._render_one(
                spec,
                field,
                pressure,
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
