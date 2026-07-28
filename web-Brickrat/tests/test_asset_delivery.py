import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import main


class AssetDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.generated = Path(self.temp.name)
        self.generated_patch = patch.object(main, "GENERATED_DIR", self.generated)
        self.generated_patch.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.generated_patch.stop()
        self.temp.cleanup()

    def make_asset(self, name: str, payload: bytes = b"model-data"):
        conversion_id = uuid4()
        root = self.generated / str(conversion_id)
        root.mkdir()
        (root / name).write_bytes(payload)
        return conversion_id

    def make_quality_conversion(self):
        conversion_id = uuid4()
        root = self.generated / str(conversion_id)
        root.mkdir()
        (root / "source.png").write_bytes(b"source")
        (root / "processed.png").write_bytes(b"processed")
        candidates = []
        for threshold in (18, 20, 22):
            candidate = root / "candidates" / f"threshold-{threshold}"
            candidate.mkdir(parents=True)
            (candidate / "model.obj").write_bytes(f"obj-{threshold}".encode())
            (candidate / "model.glb").write_bytes(f"glb-{threshold}".encode())
            (candidate / "material_report.json").write_text(json.dumps({
                "geometry_threshold": threshold,
                "glb_inspection": {"valid": True},
                "usdz_inspection": {"valid": False},
                "usdz_error": "No converter is configured.",
            }), encoding="utf-8")
            candidates.append({
                "threshold": threshold,
                "directory": f"candidates/threshold-{threshold}",
            })
        (root / "candidate_manifest.json").write_text(json.dumps({
            "version": 1,
            "resolution": 320,
            "selected_threshold": 20,
            "candidates": candidates,
        }), encoding="utf-8")
        return conversion_id

    def test_glb_preview_is_inline_with_correct_mime_and_range_support(self):
        conversion_id = self.make_asset("model.glb", b"0123456789")
        response = self.client.get(f"/models/{conversion_id}/preview/model.glb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "model/gltf-binary")
        self.assertTrue(response.headers["content-disposition"].startswith("inline"))
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertIn("no-store", response.headers["cache-control"])

        partial = self.client.get(
            f"/models/{conversion_id}/preview/model.glb", headers={"Range": "bytes=2-5"},
        )
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, b"2345")

    def test_glb_download_is_attachment(self):
        conversion_id = self.make_asset("model.glb")
        response = self.client.get(f"/models/{conversion_id}/download/model.glb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "model/gltf-binary")
        self.assertTrue(response.headers["content-disposition"].startswith("attachment"))

    def test_usdz_preview_has_quick_look_mime_and_is_inline(self):
        conversion_id = self.make_asset("model.usdz")
        response = self.client.get(f"/models/{conversion_id}/preview/model.usdz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "model/vnd.usdz+zip")
        self.assertTrue(response.headers["content-disposition"].startswith("inline"))

    def test_quality_candidate_can_be_previewed_selected_and_delivered(self):
        conversion_id = self.make_quality_conversion()

        selected = self.client.get(f"/models/{conversion_id}/preview/model.glb")
        candidate = self.client.get(
            f"/models/{conversion_id}/candidates/18/preview/model.glb",
        )
        self.assertEqual(selected.content, b"glb-20")
        self.assertEqual(candidate.content, b"glb-18")

        response = self.client.post(
            f"/conversions/{conversion_id}/candidate", data={"threshold": "22"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Choose the best geometry", response.text)
        self.assertIn("Threshold 22", response.text)
        self.assertEqual(
            self.client.get(f"/models/{conversion_id}/download/model.glb").content,
            b"glb-22",
        )
        manifest = json.loads(
            (self.generated / str(conversion_id) / "candidate_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["selected_threshold"], 22)

    def test_unknown_quality_candidate_is_rejected(self):
        conversion_id = self.make_quality_conversion()
        response = self.client.get(
            f"/models/{conversion_id}/candidates/19/preview/model.glb",
        )
        self.assertEqual(response.status_code, 404)

    def test_dimension_update_switches_delivery_to_derived_bundle_and_reset_restores_original(self):
        conversion_id = uuid4()
        root = self.generated / str(conversion_id)
        root.mkdir()
        (root / "source.png").write_bytes(b"source")
        (root / "processed.png").write_bytes(b"processed")
        (root / "model.obj").write_bytes(b"original-obj")
        (root / "model.glb").write_bytes(b"original-glb")
        (root / "material_report.json").write_text(json.dumps({
            "glb_inspection": {"valid": True},
            "usdz_inspection": {"valid": False},
        }), encoding="utf-8")

        def fake_dimensioned_bundle(work_dir, _source_dir, source_key, requested):
            output = work_dir / "dimensioned"
            output.mkdir()
            (output / "model.obj").write_bytes(b"scaled-obj")
            (output / "model.glb").write_bytes(b"scaled-glb")
            (output / "material_report.json").write_text(json.dumps({
                "glb_inspection": {"valid": True},
                "usdz_inspection": {"valid": False},
            }), encoding="utf-8")
            state = {
                "version": 1,
                "applied": True,
                "source_model": source_key,
                "requested": {
                    "width": requested.width,
                    "height": requested.height,
                    "depth": requested.depth,
                    "unit": requested.unit,
                    "width_m": requested.width_m,
                    "height_m": requested.height_m,
                    "depth_m": requested.depth_m,
                    "scaling_mode": requested.scaling_mode,
                },
                "scale_factors": {"x": 0.1, "y": 0.2, "z": 0.3},
                "final_dimensions_m": {
                    "width_m": requested.width_m,
                    "height_m": requested.height_m,
                    "depth_m": requested.depth_m,
                },
                "axis_mapping": {"x": "width", "y": "height", "z": "depth"},
                "model_orientation": "right-handed, Y-up; X=width, Y=height, Z=depth",
                "warning": None,
            }
            (output / "dimensions.json").write_text(json.dumps(state), encoding="utf-8")
            return state

        with patch.object(main, "create_dimensioned_bundle", side_effect=fake_dimensioned_bundle):
            response = self.client.post(
                f"/conversions/{conversion_id}/dimensions",
                data={
                    "width": "120",
                    "height": "80",
                    "depth": "60",
                    "unit": "cm",
                    "scaling_mode": "exact",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Metric scale applied", response.text)
        self.assertIn("1.2000 m", response.text)
        self.assertEqual(
            self.client.get(f"/models/{conversion_id}/preview/model.glb").content,
            b"scaled-glb",
        )

        reset = self.client.post(f"/conversions/{conversion_id}/dimensions/reset")
        self.assertEqual(reset.status_code, 200)
        self.assertIn("Original generated scale restored", reset.text)
        self.assertEqual(
            self.client.get(f"/models/{conversion_id}/preview/model.glb").content,
            b"original-glb",
        )

    def test_supabase_save_receives_dimension_room_and_fit_metadata(self):
        conversion_id = uuid4()
        root = self.generated / str(conversion_id)
        dimensioned = root / "dimensioned"
        dimensioned.mkdir(parents=True)
        (root / "source.png").write_bytes(b"source")
        (root / "model.obj").write_bytes(b"original-obj")
        (root / "model.glb").write_bytes(b"original-glb")
        (dimensioned / "model.obj").write_bytes(b"scaled-obj")
        (dimensioned / "model.glb").write_bytes(b"scaled-glb")
        (dimensioned / "dimensions.json").write_text(json.dumps({
            "version": 1,
            "applied": True,
            "source_model": ".",
            "requested": {
                "width": 120,
                "height": 80,
                "depth": 60,
                "unit": "cm",
                "width_m": 1.2,
                "height_m": 0.8,
                "depth_m": 0.6,
                "scaling_mode": "exact",
            },
            "scale_factors": {"x": 0.1, "y": 0.2, "z": 0.3},
            "final_dimensions_m": {
                "width_m": 1.2,
                "height_m": 0.8,
                "depth_m": 0.6,
            },
            "axis_mapping": {"x": "width", "y": "height", "z": "depth"},
            "model_orientation": "right-handed, Y-up; X=width, Y=height, Z=depth",
        }), encoding="utf-8")
        captured = {}

        def fake_save_product(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                product={"id": "saved-row", **kwargs["product"]},
                image_reused=False,
                previous_product=None,
                new_image_path=None,
            )

        try:
            with patch.object(main, "save_product", side_effect=fake_save_product):
                response = self.client.post("/products", data={
                    "conversion_id": str(conversion_id),
                    "name": "Chair",
                    "category": "Furniture",
                    "subcategory": "Chairs",
                    "table_name": "products",
                    "room_width": "4",
                    "room_length": "5",
                    "room_height": "2.5",
                    "room_unit": "m",
                    "placement_width": "2",
                    "placement_depth": "1.5",
                })
        finally:
            main.saved_products.pop(conversion_id, None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["glb_path"], dimensioned / "model.glb")
        product = captured["product"]
        self.assertEqual(product["original_unit"], "cm")
        self.assertEqual(product["width_m"], 1.2)
        self.assertEqual(product["applied_scale_factors"]["z"], 0.3)
        self.assertEqual(product["axis_mapping"]["y"], "height")
        self.assertEqual(product["room_dimensions"]["placement_area"]["depth_m"], 1.5)
        self.assertEqual(product["fit_result"]["status"], "fits")

    def test_pwa_manifest_worker_and_offline_fallback_are_served(self):
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertTrue(manifest.headers["content-type"].startswith("application/manifest+json"))
        self.assertEqual(manifest.json()["display"], "standalone")

        worker = self.client.get("/service-worker.js")
        self.assertEqual(worker.status_code, 200)
        self.assertTrue(worker.headers["content-type"].startswith("application/javascript"))
        self.assertIn(main.ASSET_VERSION, worker.text)
        self.assertNotIn("__ASSET_VERSION__", worker.text)
        self.assertEqual(worker.headers["service-worker-allowed"], "/")
        self.assertIn("no-cache", worker.headers["cache-control"])

        offline = self.client.get("/static/offline.html")
        self.assertEqual(offline.status_code, 200)
        self.assertIn("offline-shell", offline.text)

    def test_missing_and_unsafe_assets_are_rejected(self):
        conversion_id = uuid4()
        self.assertEqual(
            self.client.get(f"/models/{conversion_id}/preview/model.glb").status_code, 404,
        )
        with self.assertRaises(HTTPException) as raised:
            main._resolve_generated_asset(conversion_id, "../model.glb")
        self.assertEqual(raised.exception.status_code, 400)

    def test_external_base_url_respects_forwarded_ngrok_headers(self):
        request = Request({
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"studio-example.ngrok-free.app"),
            ],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1),
            "root_path": "",
        })
        self.assertEqual(
            main.external_base_url(request), "https://studio-example.ngrok-free.app/",
        )

    def test_post_conversion_exception_is_logged_and_result_can_be_recovered(self):
        def fake_convert(_image_path, output_dir, **_options):
            (output_dir / "processed.png").write_bytes(b"png")
            (output_dir / "model.obj").write_bytes(b"obj")
            (output_dir / "model.glb").write_bytes(b"glb")
            (output_dir / "material_report.json").write_text(json.dumps({
                "glb_inspection": {"valid": True},
                "usdz_inspection": {"valid": False},
            }), encoding="utf-8")

        failing_client = TestClient(main.app, raise_server_exceptions=False)
        try:
            with (
                patch.object(main.triposr, "convert", side_effect=fake_convert),
                patch.object(main, "_conversion_context", side_effect=RuntimeError("render failed")),
            ):
                response = failing_client.post(
                    "/convert",
                    files={"image": ("chair.png", b"image", "image/png")},
                    data={"resolution": "320", "density_threshold": "20"},
                )
        finally:
            failing_client.close()

        self.assertEqual(response.status_code, 500)
        reference = response.headers.get(main.ERROR_REFERENCE_HEADER)
        self.assertRegex(reference or "", r"^[0-9a-f]{12}$")
        self.assertIn(reference, response.text)
        self.assertIn("Recover completed conversion", response.text)
        self.assertIn(reference, main.LOG_PATH.read_text(encoding="utf-8"))

        conversions = [path for path in self.generated.iterdir() if path.is_dir()]
        self.assertEqual(len(conversions), 1)
        self.assertTrue((conversions[0] / "model.glb").is_file())
        recovered = self.client.get(f"/conversions/{conversions[0].name}")
        self.assertEqual(recovered.status_code, 200)
        self.assertIn("Your furniture model is ready", recovered.text)

    def test_conversion_result_has_sizes_public_urls_and_no_ios_ar_without_usdz(self):
        options = {}

        def fake_convert(_image_path, output_dir, **_options):
            options.update(_options)
            (output_dir / "processed.png").write_bytes(b"png")
            (output_dir / "model.obj").write_bytes(b"obj-bytes")
            (output_dir / "model.glb").write_bytes(b"glb-bytes-longer")
            (output_dir / "material_report.json").write_text(json.dumps({
                "glb_inspection": {"valid": True, "file_size": 16},
                "usdz_inspection": {"valid": False},
                "usdz_error": "No converter is configured.",
            }), encoding="utf-8")

        with patch.object(main.triposr, "convert", side_effect=fake_convert):
            response = self.client.post(
                "/convert",
                files={"image": ("chair.png", b"image", "image/png")},
                data={"density_threshold": "20"},
                headers={
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "studio-example.ngrok-free.app",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("16 bytes", response.text)
        self.assertIn("https://studio-example.ngrok-free.app/models/", response.text)
        self.assertNotIn("127.0.0.1", response.text)
        self.assertNotIn('rel="ar"', response.text)
        self.assertIn("iPhone AR file is not available", response.text)
        self.assertEqual(options["resolution"], 256)
        self.assertFalse(options["preserve_details"])
        self.assertIsNone(options["candidate_thresholds"])

    def test_quality_comparison_remains_available_when_explicitly_requested(self):
        options = {}

        def fake_convert(_image_path, output_dir, **conversion_options):
            options.update(conversion_options)
            (output_dir / "processed.png").write_bytes(b"png")
            for threshold in (18, 20, 22):
                candidate = output_dir / "candidates" / f"threshold-{threshold}"
                candidate.mkdir(parents=True)
                (candidate / "model.obj").write_bytes(b"obj")
                (candidate / "model.glb").write_bytes(b"glb")
                (candidate / "material_report.json").write_text(json.dumps({
                    "glb_inspection": {"valid": True},
                    "usdz_inspection": {"valid": False},
                }), encoding="utf-8")
            (output_dir / "candidate_manifest.json").write_text(json.dumps({
                "version": 1,
                "resolution": 320,
                "selected_threshold": 20,
                "candidates": [
                    {"threshold": value, "directory": f"candidates/threshold-{value}"}
                    for value in (18, 20, 22)
                ],
            }), encoding="utf-8")

        with patch.object(main.triposr, "convert", side_effect=fake_convert):
            response = self.client.post(
                "/convert",
                files={"image": ("chair.png", b"image", "image/png")},
                data={"resolution": "128", "density_threshold": "20", "quality_mode": "true"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(options["resolution"], 320)
        self.assertTrue(options["preserve_details"])
        self.assertEqual(options["candidate_thresholds"], main.QUALITY_THRESHOLDS)

    def test_conversion_result_exposes_valid_usdz_to_iphone_quick_look(self):
        def fake_convert(_image_path, output_dir, **_options):
            (output_dir / "processed.png").write_bytes(b"png")
            (output_dir / "model.obj").write_bytes(b"obj")
            (output_dir / "model.glb").write_bytes(b"glb")
            (output_dir / "model.usdz").write_bytes(b"validated-usdz")
            (output_dir / "material_report.json").write_text(json.dumps({
                "glb_inspection": {"valid": True, "file_size": 3},
                "usdz_inspection": {"valid": True, "file_size": 14},
            }), encoding="utf-8")

        with patch.object(main.triposr, "convert", side_effect=fake_convert):
            response = self.client.post(
                "/convert",
                files={"image": ("chair.png", b"image", "image/png")},
                data={"resolution": "320", "density_threshold": "20"},
                headers={
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "studio-example.ngrok-free.app",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Validated for Apple Quick Look", response.text)
        self.assertNotIn('rel="ar"', response.text)
        self.assertIn('data-usdz-ready="true"', response.text)
        self.assertIn("https://studio-example.ngrok-free.app/models/", response.text)
        self.assertIn("/download/model.usdz", response.text)
        self.assertIn("Apply real dimensions before opening AR", response.text)


if __name__ == "__main__":
    unittest.main()
