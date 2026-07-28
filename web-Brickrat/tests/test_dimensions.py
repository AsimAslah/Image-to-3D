import math
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dimensions import (
    AXIS_MAPPING,
    MODEL_ORIENTATION,
    calculate_scale_factors,
    check_furniture_fit,
    exact_scaling_warning,
    normalize_dimensions,
    normalize_room_dimensions,
    create_dimensioned_bundle,
    read_model_bounds,
    reset_dimensioned_bundle,
)


class DimensionMathTests(unittest.TestCase):
    def test_all_supported_units_convert_to_metres(self):
        cases = {
            "cm": (100, 200, 50),
            "mm": (1000, 2000, 500),
            "m": (1, 2, 0.5),
            "in": (39.37007874015748, 78.74015748031496, 19.68503937007874),
            "ft": (3.280839895013123, 6.561679790026246, 1.6404199475065615),
        }
        for unit, values in cases.items():
            with self.subTest(unit=unit):
                result = normalize_dimensions(*values, unit, "exact")
                self.assertAlmostEqual(result.width_m, 1.0)
                self.assertAlmostEqual(result.height_m, 2.0)
                self.assertAlmostEqual(result.depth_m, 0.5)

    def test_dimension_validation_rejects_non_positive_non_finite_and_unknown_values(self):
        invalid = (0, -1, "", "chair", math.inf, -math.inf, math.nan)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_dimensions(value, 1, 1, "m", "exact")
        with self.assertRaises(ValueError):
            normalize_dimensions(1, 1, 1, "yards", "exact")
        with self.assertRaises(ValueError):
            normalize_dimensions(1, 1, 1, "m", "approximate")

    def test_exact_scaling_matches_each_axis(self):
        factors, final = calculate_scale_factors(
            (2.0, 4.0, 8.0), (1.0, 1.0, 1.0), "exact",
        )
        self.assertEqual(factors, (0.5, 0.25, 0.125))
        self.assertEqual(final, (1.0, 1.0, 1.0))
        self.assertIsNotNone(exact_scaling_warning(factors))

    def test_preserve_scaling_uses_largest_uniform_factor_that_fits(self):
        factors, final = calculate_scale_factors(
            (2.0, 4.0, 8.0), (2.0, 2.0, 2.0), "preserve",
        )
        self.assertEqual(factors, (0.25, 0.25, 0.25))
        self.assertEqual(final, (0.5, 1.0, 2.0))
        self.assertIsNone(exact_scaling_warning(factors))

    def test_axis_mapping_and_orientation_are_explicit(self):
        self.assertEqual(AXIS_MAPPING, {"x": "width", "y": "height", "z": "depth"})
        self.assertIn("Y-up", MODEL_ORIENTATION)
        self.assertIn("X=width", MODEL_ORIENTATION)
        self.assertIn("Z=depth", MODEL_ORIENTATION)


class FurnitureFitTests(unittest.TestCase):
    def test_furniture_fits_without_rotation(self):
        result = check_furniture_fit((1.8, 0.8, 0.7), (4.0, 3.0, 2.5))
        self.assertEqual(result["status"], "fits")
        self.assertEqual(result["orientation"], "width_x_depth")
        self.assertAlmostEqual(result["clearance_m"]["width_m"], 2.2)
        self.assertAlmostEqual(result["clearance_m"]["depth_m"], 2.3)
        self.assertAlmostEqual(result["clearance_m"]["height_m"], 1.7)

    def test_furniture_fits_only_after_rotation(self):
        result = check_furniture_fit((2.0, 1.0, 1.0), (1.2, 2.2, 2.4))
        self.assertEqual(result["status"], "fits_after_rotation")
        self.assertEqual(result["orientation"], "depth_x_width")

    def test_furniture_does_not_fit_and_reports_shortage(self):
        result = check_furniture_fit((2.0, 3.0, 2.0), (1.0, 1.0, 2.5))
        self.assertEqual(result["status"], "does_not_fit")
        self.assertLess(result["clearance_m"]["height_m"], 0)

    def test_placement_area_overrides_total_floor_dimensions(self):
        result = check_furniture_fit(
            (1.5, 1.0, 1.0),
            (5.0, 5.0, 2.5),
            (1.2, 1.2),
        )
        self.assertEqual(result["status"], "does_not_fit")
        self.assertEqual(result["area_source"], "placement_area")

    def test_room_input_requires_complete_positive_placement_area(self):
        with self.assertRaises(ValueError):
            normalize_room_dimensions(4, 5, 2.5, "m", placement_width=2)
        with self.assertRaises(ValueError):
            normalize_room_dimensions(4, 5, 0, "m")
        room = normalize_room_dimensions(400, 500, 250, "cm", 200, 180)
        self.assertEqual(room["width_m"], 4.0)
        self.assertEqual(room["placement_area"]["depth_m"], 1.8)


class DimensionedExportTests(unittest.TestCase):
    def test_updates_rebuild_glb_from_original_instead_of_accumulating_scale(self):
        try:
            import numpy as np
            import trimesh
            from PIL import Image
            from trimesh.exchange.obj import export_obj
            from trimesh.visual.material import PBRMaterial
            from trimesh.visual.texture import TextureVisuals
        except ImportError:
            self.skipTest("The optional export integration dependencies are not installed.")
        if int(np.__version__.split(".", 1)[0]) >= 2:
            self.skipTest("Trimesh 4.0.5 requires the repository's pinned NumPy < 2.")

        class FakeExportService:
            @staticmethod
            def _export_obj_bundle(mesh, output_dir):
                text, resources = export_obj(
                    mesh,
                    include_normals=True,
                    include_texture=True,
                    return_texture=True,
                    mtl_name="model.mtl",
                )
                path = output_dir / "model.obj"
                path.write_text(text, encoding="utf-8")
                for filename, data in resources.items():
                    payload = data.encode("utf-8") if isinstance(data, str) else data
                    (output_dir / Path(filename).name).write_bytes(payload)
                return path, []

            @staticmethod
            def _export_usdz(_glb_path, _usdz_path, *, mesh):
                return {"valid": False, "error": "USDZ omitted in this focused GLB test."}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vertices = np.array([
                [-1, -2, -4], [1, -2, -4], [1, 2, -4], [-1, 2, -4],
                [-1, -2, 4], [1, -2, 4], [1, 2, 4], [-1, 2, 4],
            ], dtype=float)
            faces = np.array([
                [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
                [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
            ], dtype=int)
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            mesh.visual = TextureVisuals(
                uv=np.zeros((len(mesh.vertices), 2), dtype=float),
                material=PBRMaterial(
                    baseColorTexture=Image.new("RGBA", (4, 4), (120, 90, 60, 255)),
                ),
            )
            mesh.export(root / "model.glb", file_type="glb")
            fake_module = types.SimpleNamespace(triposr=FakeExportService())
            with patch.dict(sys.modules, {"triposr_service": fake_module}):
                first = create_dimensioned_bundle(
                    root, root, ".",
                    normalize_dimensions(1, 2, 3, "m", "exact"),
                )
                first_bounds = read_model_bounds(root / "dimensioned" / "model.glb")
                second = create_dimensioned_bundle(
                    root, root, ".",
                    normalize_dimensions(2, 1, 4, "m", "exact"),
                )
                second_bounds = read_model_bounds(root / "dimensioned" / "model.glb")

            self.assertEqual(read_model_bounds(root / "model.glb")["dimensions"], [2.0, 4.0, 8.0])
            for actual, expected in zip(first_bounds["dimensions"], (1.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected, places=5)
            for actual, expected in zip(second_bounds["dimensions"], (2.0, 1.0, 4.0)):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertEqual(first["scale_factors"], {"x": 0.5, "y": 0.5, "z": 0.375})
            self.assertEqual(second["scale_factors"], {"x": 1.0, "y": 0.25, "z": 0.5})
            reset_dimensioned_bundle(root)
            self.assertFalse((root / "dimensioned").exists())


if __name__ == "__main__":
    unittest.main()
