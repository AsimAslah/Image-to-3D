import tempfile
import unittest
import sys
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_diagnostics import inspect_glb
from triposr_service import triposr


def tetrahedron(colors=None):
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
        faces=np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]),
        vertex_colors=colors,
        process=False,
    )
    return mesh


class MaterialPipelineTests(unittest.TestCase):
    def test_quality_candidates_share_one_neural_inference(self):
        colors = np.array([
            [220, 35, 35, 255], [35, 210, 60, 255],
            [35, 60, 220, 255], [230, 190, 35, 255],
        ], dtype=np.uint8)

        class FakeModel:
            def __init__(self):
                self.inference_calls = 0
                self.thresholds = []

            def __call__(self, _image, *, device):
                self.inference_calls += 1
                return {"device": device}

            def extract_mesh(self, _scene_codes, _has_vertex_color, *, resolution, threshold):
                self.thresholds.append((resolution, threshold))
                return [tetrahedron(colors)]

        fake_model = FakeModel()
        unavailable_usdz = {"valid": False, "error": "not configured"}
        progress_updates = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            output = root / "output"
            Image.new("RGBA", (32, 32), "white").save(source)
            with (
                patch.object(triposr, "_load"),
                patch.object(triposr, "_model", fake_model),
                patch.object(triposr, "_export_usdz", return_value=unavailable_usdz),
            ):
                triposr.convert(
                    source, output,
                    remove_bg=False,
                    resolution=320,
                    density_threshold=20,
                    candidate_thresholds=(18, 20, 22),
                    progress_callback=lambda percent, message: progress_updates.append(
                        (percent, message)
                    ),
                )

            manifest = json.loads(
                (output / "candidate_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(fake_model.inference_calls, 1)
            self.assertEqual(fake_model.thresholds, [(320, 18.0), (320, 20.0), (320, 22.0)])
            self.assertEqual(
                [percent for percent, _message in progress_updates],
                sorted(percent for percent, _message in progress_updates),
            )
            self.assertIn((30, "Running image-to-3D neural inference..."), progress_updates)
            self.assertEqual(progress_updates[-1][0], 97)
            self.assertEqual(manifest["selected_threshold"], 20)
            for threshold in (18, 20, 22):
                candidate = output / "candidates" / f"threshold-{threshold}"
                self.assertTrue((candidate / "model.obj").is_file())
                self.assertTrue((candidate / "model.glb").is_file())

    def test_vertex_colours_become_embedded_texture(self):
        colors = np.array([
            [220, 35, 35, 255], [35, 210, 60, 255],
            [35, 60, 220, 255], [230, 190, 35, 255],
        ], dtype=np.uint8)
        mesh, report = triposr._prepare_portable_material(
            tetrahedron(colors), Image.new("RGBA", (16, 16), "white"),
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, resources = triposr._export_obj_bundle(mesh, root)
            glb = root / "model.glb"
            mesh.export(glb, file_type="glb")
            inspection = inspect_glb(glb)

            self.assertEqual(report["material_strategy"], "vertex_color_atlas")
            self.assertTrue(report["vertex_colors_preserved"])
            self.assertTrue(inspection["valid"])
            self.assertEqual(inspection["embedded_image_count"], 1)
            self.assertTrue((root / "model.mtl").is_file())
            self.assertTrue(any(Path(item["filename"]).suffix == ".png" for item in resources))

    def test_degenerate_face_is_removed_before_glb_export(self):
        colors = np.array([
            [220, 35, 35, 255], [35, 210, 60, 255],
            [35, 60, 220, 255], [230, 190, 35, 255],
        ], dtype=np.uint8)
        mesh = tetrahedron(colors)
        mesh.faces = np.vstack((mesh.faces, [0, 0, 1]))

        prepared, _ = triposr._prepare_portable_material(
            mesh, Image.new("RGBA", (16, 16), "white"),
        )

        self.assertEqual(len(prepared.faces), 4)
        self.assertTrue(np.isfinite(prepared.vertex_normals).all())
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / "model.glb"
            prepared.export(glb, file_type="glb")
            inspection = inspect_glb(glb)
        self.assertTrue(inspection["valid"], inspection.get("error"))

    def test_existing_uv_texture_is_preserved(self):
        mesh = tetrahedron()
        mesh.visual = TextureVisuals(
            uv=np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float),
            material=PBRMaterial(
                baseColorTexture=Image.new("RGB", (8, 8), (20, 80, 160)),
            ),
        )
        _, report = triposr._prepare_portable_material(
            mesh, Image.new("RGBA", (16, 16), "white"),
        )
        self.assertEqual(report["material_strategy"], "source_texture")
        self.assertTrue(report["original_texture_preserved"])
        self.assertFalse(report["fallback_material_applied"])

    def test_missing_colour_uses_image_derived_fallback(self):
        mesh = tetrahedron()
        mesh.visual = TextureVisuals(uv=None, material=None)
        prepared, report = triposr._prepare_portable_material(
            mesh, Image.new("RGBA", (16, 16), (18, 24, 32, 255)),
        )
        self.assertEqual(report["material_strategy"], "dominant_image_color_fallback")
        self.assertTrue(report["fallback_material_applied"])
        self.assertEqual(report["fallback_base_color_rgba"][:3], [18, 24, 32])
        self.assertIsNotNone(prepared.visual.material.baseColorTexture)

    def test_usdz_is_unavailable_without_converter(self):
        with patch.dict("os.environ", {}, clear=True), patch("triposr_service.shutil.which", return_value=None):
            report = triposr._export_usdz(Path("model.glb"), Path("model.usdz"))
        self.assertFalse(report["valid"])
        self.assertIn("No GLB-to-USDZ converter", report["error"])


if __name__ == "__main__":
    unittest.main()
