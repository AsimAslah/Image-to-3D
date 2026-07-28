import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main


class ConversionProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.generated = Path(self.temp.name)
        self.generated_patch = patch.object(main, "GENERATED_DIR", self.generated)
        self.generated_patch.start()
        with main.conversion_job_lock:
            main.conversion_jobs.clear()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        with main.conversion_job_lock:
            main.conversion_jobs.clear()
        self.generated_patch.stop()
        self.temp.cleanup()

    def wait_for_terminal_status(self, status_url):
        seen = []
        for _ in range(100):
            response = self.client.get(status_url)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            seen.append(payload["progress"])
            if payload["status"] in {"complete", "failed"}:
                return payload, seen
            time.sleep(0.01)
        self.fail("Conversion job did not reach a terminal state.")

    @staticmethod
    def create_valid_result(output_dir):
        (output_dir / "processed.png").write_bytes(b"png")
        (output_dir / "model.obj").write_bytes(b"obj")
        (output_dir / "model.glb").write_bytes(b"glb")
        (output_dir / "material_report.json").write_text(json.dumps({
            "glb_inspection": {"valid": True, "file_size": 3},
            "usdz_inspection": {"valid": False},
        }), encoding="utf-8")

    def test_background_job_reports_progress_and_uses_fast_defaults(self):
        options = {}

        def fake_convert(_image_path, output_dir, **conversion_options):
            options.update(conversion_options)
            callback = conversion_options["progress_callback"]
            for percent, message in (
                (10, "Loading model"),
                (30, "Running inference"),
                (48, "Building geometry"),
                (82, "Exporting GLB"),
                (97, "Validating"),
            ):
                callback(percent, message)
            self.create_valid_result(output_dir)

        with patch.object(main.triposr, "convert", side_effect=fake_convert):
            started = self.client.post(
                "/api/conversions",
                files={"image": ("chair.png", b"image", "image/png")},
                data={"density_threshold": "20"},
            )
            self.assertEqual(started.status_code, 202)
            payload, seen = self.wait_for_terminal_status(started.json()["status_url"])

        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["progress"], 100)
        self.assertEqual(sorted(seen), seen)
        self.assertEqual(options["resolution"], 256)
        self.assertFalse(options["preserve_details"])
        self.assertIsNone(options["candidate_thresholds"])
        result = self.client.get(payload["result_url"])
        self.assertEqual(result.status_code, 200)
        self.assertIn("Your furniture model is ready", result.text)

    def test_background_job_returns_safe_failure_with_reference(self):
        def fail_conversion(_image_path, _output_dir, **conversion_options):
            conversion_options["progress_callback"](30, "Running inference")
            raise RuntimeError("private failure detail")

        with patch.object(main.triposr, "convert", side_effect=fail_conversion):
            started = self.client.post(
                "/api/conversions",
                files={"image": ("chair.png", b"image", "image/png")},
            )
            payload, seen = self.wait_for_terminal_status(started.json()["status_url"])

        self.assertEqual(payload["status"], "failed")
        self.assertGreaterEqual(max(seen), 30)
        self.assertNotIn("private failure detail", json.dumps(payload))
        self.assertRegex(payload["error_reference"], r"^[0-9a-f]{12}$")

    def test_second_conversion_is_rejected_while_one_is_active(self):
        self.assertTrue(main.conversion_lock.acquire(blocking=False))
        try:
            response = self.client.post(
                "/api/conversions",
                files={"image": ("chair.png", b"image", "image/png")},
            )
        finally:
            main.conversion_lock.release()

        self.assertEqual(response.status_code, 409)
        self.assertIn("already running", response.json()["detail"])

    def test_missing_image_returns_readable_validation_error(self):
        response = self.client.post(
            "/api/conversions",
            data={"density_threshold": "20"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "image: Field required")


if __name__ == "__main__":
    unittest.main()
