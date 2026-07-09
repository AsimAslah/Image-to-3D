import threading
import sys
from pathlib import Path

import numpy as np
import rembg
import torch
from PIL import Image
from PIL import ImageOps

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground, to_gradio_3d_orientation


class TripoSRService:
    """Lazy, process-local wrapper around the TripoSR model."""

    def __init__(self) -> None:
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._rembg_session = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            self._model = TSR.from_pretrained(
                "stabilityai/TripoSR",
                config_name="config.yaml",
                weight_name="model.ckpt",
            )
            self._model.renderer.set_chunk_size(8192)
            self._model.to(self.device)
            self._rembg_session = rembg.new_session()

    @staticmethod
    def _fill_background(image: Image.Image) -> Image.Image:
        rgba = np.asarray(image).astype(np.float32) / 255.0
        rgb = rgba[:, :, :3] * rgba[:, :, 3:4] + (1 - rgba[:, :, 3:4]) * 0.5
        return Image.fromarray((rgb * 255.0).astype(np.uint8))

    def convert(
        self,
        image_path: Path,
        output_dir: Path,
        *,
        remove_bg: bool = True,
        foreground_ratio: float = 0.85,
        resolution: int = 256,
        preserve_details: bool = True,
        density_threshold: float = 20.0,
    ) -> tuple[Path, Path]:
        self._load()
        image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGBA")
        if remove_bg:
            rembg_options = {}
            if preserve_details:
                rembg_options = {
                    "alpha_matting": True,
                    "alpha_matting_foreground_threshold": 240,
                    "alpha_matting_background_threshold": 10,
                    "alpha_matting_erode_size": 0,
                }
            image = remove_background(
                image.convert("RGB"), self._rembg_session, **rembg_options,
            )
            image = resize_foreground(image, foreground_ratio)
        if image.mode == "RGBA":
            image = self._fill_background(image)

        output_dir.mkdir(parents=True, exist_ok=True)
        image.save(output_dir / "processed.png", optimize=True)
        obj_path = output_dir / "model.obj"
        glb_path = output_dir / "model.glb"
        with self._inference_lock, torch.no_grad():
            scene_codes = self._model(image, device=self.device)
            mesh = self._model.extract_mesh(
                scene_codes, True, resolution=resolution,
                threshold=density_threshold,
            )[0]
            mesh.remove_unreferenced_vertices()
            mesh.fix_normals()
            mesh = to_gradio_3d_orientation(mesh)
            mesh.export(obj_path)
            mesh.export(glb_path)
        return obj_path, glb_path


triposr = TripoSRService()
