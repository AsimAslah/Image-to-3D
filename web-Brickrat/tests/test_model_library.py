import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main
import supabase_store


class FakeLibraryQuery:
    def __init__(self, rows):
        self.rows = rows
        self.selected = None
        self.maximum = None

    def select(self, fields):
        self.selected = fields
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows[: self.maximum])


class FakeLibraryClient:
    def __init__(self, rows):
        self.query = FakeLibraryQuery(rows)
        self.table_name = None

    def table(self, table_name):
        self.table_name = table_name
        return self.query


class ModelLibraryStoreTests(unittest.TestCase):
    def list_models(self, rows, table_name="products"):
        client = FakeLibraryClient(rows)
        with (
            patch.object(supabase_store, "_client", return_value=client),
            patch.dict(os.environ, {"SUPABASE_PRODUCTS_TABLE": table_name}),
        ):
            models = supabase_store.list_models()
        return models, client

    def test_multiple_models_are_sanitized_and_sorted_newest_first(self):
        models, client = self.list_models([
            {
                "id": "older",
                "name": "Oak chair",
                "category": "Chairs",
                "description": "Solid oak",
                "price": "249.50",
                "image_url": "https://assets.test/chair.png",
                "model_url": "https://assets.test/chair.glb?download=1",
                "usdz_url": "https://assets.test/chair.usdz",
                "obj_url": "https://assets.test/chair.obj",
                "width": 70,
                "height": 90,
                "depth": 75,
                "original_unit": "cm",
                "created_at": "2026-06-01T10:00:00Z",
                "image_sha256": "must-not-leak",
                "room_dimensions": {"private": "must-not-leak"},
            },
            {
                "id": "newer",
                "name": "Walnut table",
                "model_url": "https://assets.test/table.glb",
                "created_at": "2026-07-01T10:00:00+00:00",
            },
        ])

        self.assertEqual([model["id"] for model in models], ["newer", "older"])
        self.assertEqual(models[1]["price"], 249.5)
        self.assertEqual(
            models[1]["dimensions"],
            {"width": 70.0, "height": 90.0, "depth": 75.0, "unit": "cm"},
        )
        self.assertNotIn("image_sha256", models[1])
        self.assertNotIn("room_dimensions", models[1])
        self.assertEqual(client.table_name, "products")
        self.assertEqual(client.query.selected, "*")
        self.assertEqual(client.query.maximum, 200)

    def test_missing_optional_fields_are_returned_as_null(self):
        models, _ = self.list_models([{"id": "minimal", "name": "Minimal model"}])

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["name"], "Minimal model")
        for field in (
            "category", "description", "price", "dimensions", "created_at",
            "thumbnail_url", "glb_url", "usdz_url", "obj_url",
        ):
            self.assertIsNone(models[0][field], field)

    def test_glb_without_usdz_remains_available(self):
        models, _ = self.list_models([{
            "name": "Android model",
            "model_url": "https://assets.test/model.glb",
            "usdz_url": None,
        }])

        self.assertEqual(models[0]["glb_url"], "https://assets.test/model.glb")
        self.assertIsNone(models[0]["usdz_url"])

    def test_invalid_or_wrong_format_urls_are_removed(self):
        models, _ = self.list_models([{
            "name": "Unsafe model",
            "image_url": "javascript:alert(1)",
            "model_url": "https://assets.test/model.obj",
            "usdz_url": "https://user:password@assets.test/model.usdz",
            "obj_url": "not-a-url",
            "created_at": "not-a-date",
        }])

        for field in ("thumbnail_url", "glb_url", "usdz_url", "obj_url", "created_at"):
            self.assertIsNone(models[0][field], field)

    def test_final_metric_dimensions_are_used_when_original_fields_are_missing(self):
        models, _ = self.list_models([{
            "name": "Metric model",
            "final_dimensions_m": {
                "width_m": 1.2,
                "height_m": 0.8,
                "depth_m": 0.6,
            },
        }])

        self.assertEqual(
            models[0]["dimensions"],
            {"width": 1.2, "height": 0.8, "depth": 0.6, "unit": "m"},
        )


class ModelLibraryApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_api_returns_multiple_models_with_no_store_headers(self):
        rows = [
            {"id": "one", "name": "Chair", "glb_url": "https://assets.test/one.glb"},
            {"id": "two", "name": "Table", "glb_url": "https://assets.test/two.glb"},
        ]
        with patch.object(main, "list_models", return_value=rows):
            response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"models": rows, "count": 2})
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_api_returns_an_empty_collection(self):
        with patch.object(main, "list_models", return_value=[]):
            response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"models": [], "count": 0})

    def test_api_reports_missing_supabase_configuration(self):
        with patch.object(
            main,
            "list_models",
            side_effect=supabase_store.SupabaseNotConfigured("Set the server configuration."),
        ):
            response = self.client.get("/api/models")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Set the server configuration.")

    def test_api_hides_upstream_failure_details(self):
        failing_client = TestClient(main.app, raise_server_exceptions=False)
        with patch.object(
            main,
            "list_models",
            side_effect=RuntimeError("secret-key-value upstream failure"),
        ):
            response = failing_client.get("/api/models")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Saved models are temporarily unavailable.")
        self.assertNotIn("secret-key-value", response.text)
        self.assertIn("error_reference", response.json())


if __name__ == "__main__":
    unittest.main()
