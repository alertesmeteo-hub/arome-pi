from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from arome_maps import AromeMapRenderer  # noqa: E402
from update_arome_pi import (  # noqa: E402
    API_FIELDS,
    IncompleteRunError,
    Resource,
    choose_resources,
    grid_index,
    load_catalog,
    transform_step,
    wait_for_complete_remote_run,
)


class AromePipelineTests(unittest.TestCase):
    def test_current_meteofrance_wcs_coverage_names(self) -> None:
        self.assertEqual(API_FIELDS["TEMPERATURE"][0], "T__HEIGHT")
        self.assertEqual(API_FIELDS["PRECIPITATION"][0], "PRECIP__GROUND")
        self.assertEqual(API_FIELDS["PRESSURE"][0], "P__SEA")
        self.assertEqual(API_FIELDS["GUST_MAX"][0], "FF_RAF_MAX__HEIGHT")

    @staticmethod
    def resource(group: str, lead: int, run: str) -> Resource:
        return Resource(
            group=group,
            lead=lead,
            run_text=run,
            title=f"arome__001__{group}__{lead:02d}H__{run}.grib2",
            url="https://example.invalid/arome.grib2",
            size=1,
            local_path=None,
        )

    def test_resource_selection_never_mixes_runs(self) -> None:
        run_a = "2026-08-21T06:00:00Z"
        run_b = "2026-08-21T09:00:00Z"
        resources = [
            *(self.resource(group, lead, run_b) for group in API_FIELDS for lead in range(1, 3)),
        ]
        resources = [
            r
            for r in resources
            if not (r.group == "PRECIPITATION" and r.run_text == run_b)
        ]
        resources.extend(
            self.resource("PRECIPITATION", lead, run_a) for lead in range(1, 3)
        )
        with self.assertRaisesRegex(
            IncompleteRunError, "Catalogue AROME-PI en cours de synchronisation"
        ):
            choose_resources(resources, 2)

    def test_resource_selection_uses_previous_stable_run(self) -> None:
        older = "2026-08-21T06:00:00Z"
        latest = "2026-08-21T09:00:00Z"
        resources = []
        for run in (older, latest):
            resources.extend(
                self.resource(group, lead, run)
                for group in API_FIELDS
                for lead in range(1, 3)
            )
        selected, run_time = choose_resources(resources, 2)
        self.assertEqual(run_time, datetime(2026, 8, 21, 6, tzinfo=timezone.utc))
        self.assertEqual(selected["GUST_U", 2].run_text, older)
        self.assertEqual(selected["REFLECTIVITY", 1].run_text, older)

    def test_resource_selection_accepts_missing_optional_field(self) -> None:
        run = "2026-08-21T09:00:00Z"
        resources = [
            self.resource(group, lead, run)
            for group in API_FIELDS
            for lead in range(1, 3)
            if group != "ISO_ZERO"
        ]
        selected, run_time = choose_resources(resources, 2)
        self.assertEqual(run_time, datetime(2026, 8, 21, 9, tzinfo=timezone.utc))
        self.assertNotIn(("ISO_ZERO", 1), selected)

    def test_catalog_retry_accepts_run_after_transient_replacement(self) -> None:
        old = "2026-08-21T06:00:00Z"
        new = "2026-08-21T09:00:00Z"
        mixed = [
            *(self.resource(group, lead, new) for group in API_FIELDS for lead in range(1, 2)),
        ]
        mixed = [
            r
            for r in mixed
            if not (r.group == "PRECIPITATION" and r.run_text == new)
        ]
        mixed.extend(
            self.resource("PRECIPITATION", lead, old) for lead in range(1, 2)
        )
        complete = [
            *(
                self.resource(group, lead, new)
                for group in API_FIELDS
                for lead in range(1, 2)
            ),
        ]
        with patch(
            "update_arome_pi.api_resources", side_effect=(mixed, complete)
        ) as mocked_api:
            selection = wait_for_complete_remote_run(object(), 1, 2, 0)
        self.assertIsNotNone(selection)
        self.assertEqual(mocked_api.call_count, 2)
        self.assertEqual(selection[1], datetime(2026, 8, 21, 9, tzinfo=timezone.utc))

    def test_catalog_is_remapped_to_arome_grid(self) -> None:
        catalog = load_catalog(ROOT / "config" / "communes-france.json")
        self.assertEqual(catalog.commune_count, 34746)
        self.assertEqual(len(catalog.departments), 96)
        self.assertGreater(len(catalog.model_indexes), 34000)
        perpignan = next(
            commune
            for commune in catalog.departments["66"].communes
            if commune[0] == "66136"
        )
        point = catalog.departments["66"].points[perpignan[6]]
        expected_index, latitude, longitude = grid_index(42.699, 2.9045)
        self.assertEqual(point[0], expected_index)
        self.assertAlmostEqual(point[1], latitude, places=5)
        self.assertAlmostEqual(point[2], longitude, places=5)

    def test_accumulations_and_derived_pressure(self) -> None:
        shape = (2,)
        altitude = np.asarray([0.0, 500.0])
        common = {
            "temperature_k": np.asarray([283.15, 273.15]),
            "humidity_pct": np.asarray([80.0, 90.0]),
            "wind_u_ms": np.asarray([3.0, 4.0]),
            "wind_v_ms": np.asarray([4.0, 3.0]),
            "gust_u_ms": np.asarray([6.0, 8.0]),
            "gust_v_ms": np.asarray([8.0, 6.0]),
            "surface_pressure_pa": np.asarray([101300.0, 95000.0]),
            "cape_jkg": np.asarray([0.0, 1500.0]),
            "reflectivity_dbz": np.asarray([0.0, 52.0]),
            "cloud_low_pct": np.asarray([10.0, 70.0]),
            "cloud_mid_pct": np.asarray([20.0, 50.0]),
            "cloud_high_pct": np.asarray([30.0, 20.0]),
        }
        first = dict(common)
        first.update(
            {
                "precipitation_total_mm": np.asarray([0.0, 1.0]),
                "snow_total_mm": np.asarray([0.0, 0.2]),
                "graupel_total_mm": np.asarray([0.0, 0.1]),
            }
        )
        transformed, state = transform_step(first, altitude, {}, 1)
        second = dict(common)
        second.update(
            {
                "precipitation_total_mm": np.asarray([0.5, 3.5]),
                "snow_total_mm": np.asarray([0.0, 0.7]),
                "graupel_total_mm": np.asarray([0.0, 0.3]),
            }
        )
        transformed2, _state2 = transform_step(second, altitude, state, 2)
        np.testing.assert_allclose(transformed2["precipitation_mm"], [0.5, 2.5])
        np.testing.assert_allclose(transformed2["snowfall_mm"], [0.0, 0.5])
        self.assertGreater(transformed["pressure_hpa"][1], 950)
        self.assertEqual(int(transformed["thunder_risk_code"][1]), 3)
        self.assertEqual(transformed["temperature_c"].shape, shape)

    def test_hourly_api_precipitation_is_accumulated_without_subtraction(self) -> None:
        shape = (2,)
        altitude = np.zeros(shape)
        first, state = transform_step(
            {
                "precipitation_hourly_mm": np.asarray([0.2, 1.5]),
                "pressure_msl_pa": np.asarray([101200.0, 100500.0]),
            },
            altitude,
            {},
            1,
        )
        second, _state = transform_step(
            {"precipitation_hourly_mm": np.asarray([0.4, 2.0])},
            altitude,
            state,
            2,
        )
        np.testing.assert_allclose(first["precipitation_mm"], [0.2, 1.5])
        np.testing.assert_allclose(second["precipitation_mm"], [0.4, 2.0])
        np.testing.assert_allclose(second["precipitation_total_mm"], [0.6, 3.5])
        np.testing.assert_allclose(first["pressure_hpa"], [1012.0, 1005.0])

    def test_pregridded_renderer_and_static_altitude(self) -> None:
        with tempfile.TemporaryDirectory(prefix="arome-map-test-") as temporary:
            destination = Path(temporary) / "maps"
            renderer = AromeMapRenderer(
                np.empty(0),
                np.empty(0),
                destination,
                width=80,
                height=60,
                pregridded=True,
            )
            temperature = np.linspace(5, 25, 80 * 60).reshape(60, 80)
            altitude = np.linspace(0, 1000, 80 * 60).reshape(60, 80)
            renderer.render_step(
                lead_hour=0,
                valid_time=datetime(2026, 8, 21, 6, tzinfo=timezone.utc),
                fields={"temperature_c": temperature, "altitude_m": altitude},
            )
            renderer.render_step(
                lead_hour=1,
                valid_time=datetime(2026, 8, 21, 7, tzinfo=timezone.utc),
                fields={"temperature_c": temperature + 1, "altitude_m": altitude},
            )
            manifest = renderer.write_manifest(
                generated_at="2026-08-21T06:30:00Z",
                run_time="2026-08-21T06:00:00Z",
            )
            self.assertEqual(len(manifest["steps"]), 2)
            self.assertEqual(
                manifest["steps"][0]["files"]["altitude"],
                manifest["steps"][1]["files"]["altitude"],
            )
            self.assertTrue((destination / "temperature/000.webp").is_file())
            self.assertTrue((destination / "values/temperature/000.hkv.gz").is_file())
            disk_manifest = json.loads((destination / "index.json").read_text())
            self.assertEqual(disk_manifest["status"], "ok")


if __name__ == "__main__":
    unittest.main()

