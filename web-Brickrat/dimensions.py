"""Dimension validation, physical scaling, and furniture-fit calculations."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4


UNIT_TO_METRES = {
    "cm": 0.01,
    "mm": 0.001,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}
SCALING_MODES = {"preserve", "exact"}
AXIS_MAPPING = {"x": "width", "y": "height", "z": "depth"}
MODEL_ORIENTATION = "right-handed, Y-up; X=width, Y=height, Z=depth"
EPSILON = 1e-9


@dataclass(frozen=True)
class DimensionInput:
    width: float
    height: float
    depth: float
    unit: str
    width_m: float
    height_m: float
    depth_m: float
    scaling_mode: str

    @property
    def metres(self) -> tuple[float, float, float]:
        return self.width_m, self.height_m, self.depth_m


def _positive_number(value: float | int | str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive number.") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a positive number.")
    return number


def normalize_dimensions(
    width: float | str,
    height: float | str,
    depth: float | str,
    unit: str,
    scaling_mode: str,
) -> DimensionInput:
    """Validate user input and normalize it to metres."""
    canonical_unit = str(unit).strip().lower()
    if canonical_unit not in UNIT_TO_METRES:
        raise ValueError("Unit must be cm, mm, m, in, or ft.")
    canonical_mode = str(scaling_mode).strip().lower()
    if canonical_mode not in SCALING_MODES:
        raise ValueError("Scaling mode must be preserve or exact.")
    width_value = _positive_number(width, "Width")
    height_value = _positive_number(height, "Height")
    depth_value = _positive_number(depth, "Depth")
    multiplier = UNIT_TO_METRES[canonical_unit]
    return DimensionInput(
        width=width_value,
        height=height_value,
        depth=depth_value,
        unit=canonical_unit,
        width_m=width_value * multiplier,
        height_m=height_value * multiplier,
        depth_m=depth_value * multiplier,
        scaling_mode=canonical_mode,
    )


def calculate_scale_factors(
    original_dimensions: Iterable[float],
    requested_dimensions_m: Iterable[float],
    scaling_mode: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return X/Y/Z scales and final X/Y/Z dimensions in metres.

    Preserve mode uses the largest uniform factor whose result fits inside all
    three requested dimensions. Exact mode independently matches every axis.
    """
    original = tuple(
        _positive_number(value, f"Original {axis} dimension")
        for value, axis in zip(original_dimensions, ("X", "Y", "Z"), strict=True)
    )
    requested = tuple(
        _positive_number(value, f"Requested {axis} dimension")
        for value, axis in zip(requested_dimensions_m, ("X", "Y", "Z"), strict=True)
    )
    if scaling_mode not in SCALING_MODES:
        raise ValueError("Scaling mode must be preserve or exact.")
    ratios = tuple(target / source for target, source in zip(requested, original))
    factors = (min(ratios),) * 3 if scaling_mode == "preserve" else ratios
    final = tuple(source * factor for source, factor in zip(original, factors))
    return factors, final


def exact_scaling_warning(scale_factors: Iterable[float]) -> str | None:
    factors = tuple(float(value) for value in scale_factors)
    if len(factors) != 3:
        raise ValueError("Three scale factors are required.")
    if max(factors) / min(factors) > 1.05:
        return (
            "Exact dimensions use different X, Y, and Z scale factors. "
            "This can visibly stretch or squash the furniture."
        )
    return None


def _three_values(values, label: str) -> tuple[float, float, float]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must contain three numeric values.") from None
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{label} must contain three finite numeric values.")
    return result


def check_furniture_fit(
    furniture_dimensions_m: Iterable[float],
    room_dimensions_m: Iterable[float],
    placement_area_m: Iterable[float] | None = None,
) -> dict:
    """Check direct and 90-degree floor orientations.

    Inputs use (width, height, depth) for furniture and
    (width, length, height) for the room.
    """
    furniture_width, furniture_height, furniture_depth = _three_values(
        furniture_dimensions_m, "Furniture dimensions",
    )
    room_width, room_length, room_height = _three_values(
        room_dimensions_m, "Room dimensions",
    )
    for value, label in (
        (furniture_width, "Furniture width"),
        (furniture_height, "Furniture height"),
        (furniture_depth, "Furniture depth"),
        (room_width, "Room width"),
        (room_length, "Room length"),
        (room_height, "Room height"),
    ):
        _positive_number(value, label)

    area_width, area_depth = room_width, room_length
    area_source = "room"
    if placement_area_m is not None:
        try:
            placement = tuple(float(value) for value in placement_area_m)
        except (TypeError, ValueError):
            raise ValueError("Placement area must contain width and depth.") from None
        if len(placement) != 2 or not all(math.isfinite(value) for value in placement):
            raise ValueError("Placement area must contain finite width and depth.")
        area_width, area_depth = placement
        _positive_number(area_width, "Placement-area width")
        _positive_number(area_depth, "Placement-area depth")
        area_source = "placement_area"

    direct_clearance = {
        "width_m": area_width - furniture_width,
        "depth_m": area_depth - furniture_depth,
        "height_m": room_height - furniture_height,
    }
    rotated_clearance = {
        "width_m": area_width - furniture_depth,
        "depth_m": area_depth - furniture_width,
        "height_m": room_height - furniture_height,
    }
    tolerance = 1e-9
    direct_fits = min(direct_clearance.values()) >= -tolerance
    rotated_fits = min(rotated_clearance.values()) >= -tolerance

    if direct_fits:
        status, orientation, clearance = "fits", "width_x_depth", direct_clearance
    elif rotated_fits:
        status, orientation, clearance = (
            "fits_after_rotation", "depth_x_width", rotated_clearance,
        )
    else:
        direct_score = min(direct_clearance.values())
        rotated_score = min(rotated_clearance.values())
        if rotated_score > direct_score:
            orientation, clearance = "depth_x_width", rotated_clearance
        else:
            orientation, clearance = "width_x_depth", direct_clearance
        status = "does_not_fit"

    return {
        "status": status,
        "orientation": orientation,
        "area_source": area_source,
        "clearance_m": clearance,
        "direct": {"fits": direct_fits, "clearance_m": direct_clearance},
        "rotated": {"fits": rotated_fits, "clearance_m": rotated_clearance},
    }


def normalize_room_dimensions(
    width: float | str,
    length: float | str,
    height: float | str,
    unit: str,
    placement_width: float | str | None = None,
    placement_depth: float | str | None = None,
) -> dict:
    canonical_unit = str(unit).strip().lower()
    if canonical_unit not in UNIT_TO_METRES:
        raise ValueError("Room unit must be cm, mm, m, in, or ft.")
    width_value = _positive_number(width, "Room width")
    length_value = _positive_number(length, "Room length")
    height_value = _positive_number(height, "Room height")
    multiplier = UNIT_TO_METRES[canonical_unit]
    room = {
        "width": width_value,
        "length": length_value,
        "height": height_value,
        "unit": canonical_unit,
        "width_m": width_value * multiplier,
        "length_m": length_value * multiplier,
        "height_m": height_value * multiplier,
    }
    supplied = (placement_width not in (None, ""), placement_depth not in (None, ""))
    if any(supplied) and not all(supplied):
        raise ValueError("Enter both placement-area width and depth, or leave both blank.")
    if all(supplied):
        area_width = _positive_number(placement_width, "Placement-area width")
        area_depth = _positive_number(placement_depth, "Placement-area depth")
        room["placement_area"] = {
            "width": area_width,
            "depth": area_depth,
            "unit": canonical_unit,
            "width_m": area_width * multiplier,
            "depth_m": area_depth * multiplier,
        }
    else:
        room["placement_area"] = None
    return room


def read_model_bounds(glb_path: Path) -> dict:
    """Read a GLB scene bounding box without assuming its source units."""
    import numpy as np
    import trimesh

    scene = trimesh.load(str(glb_path), force="scene", process=False)
    bounds = np.asarray(scene.bounds, dtype=float)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all():
        raise ValueError("The generated model has an invalid bounding box.")
    dimensions = bounds[1] - bounds[0]
    if not np.isfinite(dimensions).all() or (dimensions <= EPSILON).any():
        raise ValueError("The generated model bounding box has a zero or invalid axis.")
    return {
        "min": bounds[0].tolist(),
        "max": bounds[1].tolist(),
        "dimensions": dimensions.tolist(),
    }


def read_usdz_dimensions_m(usdz_path: Path) -> tuple[float, float, float]:
    """Measure a USDZ world bound and convert its authored units to metres."""
    try:
        from pxr import Usd, UsdGeom
    except ImportError as exc:
        raise ValueError("OpenUSD is required to verify USDZ dimensions.") from exc

    stage = Usd.Stage.Open(str(usdz_path))
    if stage is None:
        raise ValueError("The scaled USDZ stage could not be opened.")
    prim = stage.GetDefaultPrim()
    if not prim:
        prim = stage.GetPseudoRoot()
    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]
    world_bound = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), purposes, useExtentsHint=True,
    ).ComputeWorldBound(prim).ComputeAlignedRange()
    minimum = world_bound.GetMin()
    maximum = world_bound.GetMax()
    metres_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage))
    dimensions = tuple(
        (float(maximum[index]) - float(minimum[index])) * metres_per_unit
        for index in range(3)
    )
    if not all(math.isfinite(value) and value > EPSILON for value in dimensions):
        raise ValueError("The scaled USDZ has an invalid world bounding box.")
    return dimensions


def _write_scaled_assets(source_dir: Path, output_dir: Path, factors: tuple[float, ...]) -> dict:
    import numpy as np
    import trimesh

    from model_diagnostics import inspect_glb
    from triposr_service import triposr

    source_glb = source_dir / "model.glb"
    if not source_glb.is_file():
        raise FileNotFoundError("The original generated GLB was not found.")
    scene = trimesh.load(str(source_glb), force="scene", process=False)
    scaled_scene = scene.scaled(factors)
    output_dir.mkdir(parents=True, exist_ok=True)

    glb_path = output_dir / "model.glb"
    scaled_scene.export(file_obj=str(glb_path), file_type="glb")
    glb_report = inspect_glb(glb_path)
    if not glb_report.get("valid"):
        raise RuntimeError(glb_report.get("error", "Scaled GLB validation failed."))

    mesh = scaled_scene.dump(concatenate=True)
    obj_path, obj_resources = triposr._export_obj_bundle(mesh, output_dir)
    usdz_path = output_dir / "model.usdz"
    usdz_report = triposr._export_usdz(glb_path, usdz_path, mesh=mesh)
    if usdz_report.get("valid"):
        try:
            glb_dimensions = tuple(read_model_bounds(glb_path)["dimensions"])
            usdz_dimensions = read_usdz_dimensions_m(usdz_path)
            if not np.allclose(glb_dimensions, usdz_dimensions, rtol=1e-4, atol=1e-5):
                raise ValueError(
                    "USDZ dimensions do not match the dimensionally scaled GLB."
                )
            usdz_report["dimensions_m"] = list(usdz_dimensions)
            usdz_report["dimensions_match_glb"] = True
        except (OSError, TypeError, ValueError) as exc:
            usdz_path.unlink(missing_ok=True)
            usdz_report = {
                **usdz_report,
                "valid": False,
                "dimensions_match_glb": False,
                "error": f"USDZ dimension verification failed: {exc}",
            }

    source_report_path = source_dir / "material_report.json"
    try:
        report = json.loads(source_report_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        report = {}
    report.update({
        "glb_inspection": glb_report,
        "usdz_inspection": usdz_report,
        "usdz_created": bool(usdz_report.get("valid")),
        "obj_resources": obj_resources,
        "dimensionally_scaled": True,
    })
    if not usdz_report.get("valid"):
        report["usdz_error"] = usdz_report.get("error", "Scaled USDZ validation failed.")
    else:
        report.pop("usdz_error", None)
    (output_dir / "material_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )
    return {
        "obj_path": obj_path,
        "glb_path": glb_path,
        "usdz_path": usdz_path if usdz_report.get("valid") else None,
        "glb_inspection": glb_report,
        "usdz_inspection": usdz_report,
    }


def create_dimensioned_bundle(
    work_dir: Path,
    source_dir: Path,
    source_key: str,
    requested: DimensionInput,
) -> dict:
    """Build and atomically publish a freshly scaled model bundle."""
    original_bounds = read_model_bounds(source_dir / "model.glb")
    factors, calculated_final = calculate_scale_factors(
        original_bounds["dimensions"], requested.metres, requested.scaling_mode,
    )
    temporary = work_dir / f".dimensioned-{uuid4().hex}"
    destination = work_dir / "dimensioned"
    backup = work_dir / f".dimensioned-backup-{uuid4().hex}"
    try:
        assets = _write_scaled_assets(source_dir, temporary, factors)
        measured = read_model_bounds(assets["glb_path"])["dimensions"]
        state = {
            "version": 1,
            "applied": True,
            "source_model": source_key,
            "requested": asdict(requested),
            "original_bbox": original_bounds,
            "scale_factors": {"x": factors[0], "y": factors[1], "z": factors[2]},
            "calculated_final_dimensions_m": {
                "width_m": calculated_final[0],
                "height_m": calculated_final[1],
                "depth_m": calculated_final[2],
            },
            "final_dimensions_m": {
                "width_m": measured[0],
                "height_m": measured[1],
                "depth_m": measured[2],
            },
            "axis_mapping": AXIS_MAPPING,
            "model_orientation": MODEL_ORIENTATION,
            "warning": exact_scaling_warning(factors)
            if requested.scaling_mode == "exact" else None,
        }
        (temporary / "dimensions.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8",
        )

        if destination.exists():
            destination.replace(backup)
        temporary.replace(destination)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        return state
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if backup.exists() and not destination.exists():
            backup.replace(destination)
        raise


def load_dimension_state(work_dir: Path, source_key: str) -> dict | None:
    path = work_dir / "dimensioned" / "dimensions.json"
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(state, dict) or state.get("source_model") != source_key:
        return None
    try:
        requested = state["requested"]
        final = state["final_dimensions_m"]
        factors = state["scale_factors"]
        normalize_dimensions(
            requested["width"], requested["height"], requested["depth"],
            requested["unit"], requested["scaling_mode"],
        )
        for key in ("width_m", "height_m", "depth_m"):
            _positive_number(final[key], f"Final {key}")
        for key in ("x", "y", "z"):
            _positive_number(factors[key], f"Scale factor {key}")
    except (KeyError, TypeError, ValueError):
        return None
    if not all((work_dir / "dimensioned" / name).is_file() for name in ("model.glb", "model.obj")):
        return None
    return state


def reset_dimensioned_bundle(work_dir: Path) -> None:
    destination = work_dir / "dimensioned"
    if destination.is_dir():
        shutil.rmtree(destination)
