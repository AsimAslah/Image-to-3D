import shutil
import threading
import mimetypes
import json
import hashlib
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urljoin
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from dimensions import (
    check_furniture_fit,
    create_dimensioned_bundle,
    load_dimension_state,
    normalize_dimensions,
    normalize_room_dimensions,
    reset_dimensioned_bundle,
)
from room_capture import RoomPlanCapture, model_payload
from supabase_store import (
    SupabaseNotConfigured, list_models, save_product, undo_product_save,
    validate_table_name,
)
from triposr_service import triposr
from model_diagnostics import inspect_model

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)
mimetypes.add_type("model/vnd.usdz+zip", ".usdz")
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("text/plain", ".obj")
mimetypes.add_type("text/plain", ".mtl")


def _asset_version() -> str:
    digest = hashlib.sha256()
    static_dir = BASE_DIR / "static"
    for path in sorted(item for item in static_dir.rglob("*") if item.is_file()):
        digest.update(path.relative_to(static_dir).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


ASSET_VERSION = _asset_version()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG_PATH = Path(os.getenv("APP_LOG_PATH", str(BASE_DIR / "server.log"))).resolve()


def _configure_persistent_logging() -> None:
    """Keep exception traces across terminal closes and server restarts."""
    root_logger = logging.getLogger()
    if any(getattr(handler, "_furniture_ar_persistent", False) for handler in root_logger.handlers):
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding="utf-8", delay=True,
        )
    except OSError:
        logging.getLogger("furniture_ar.web").exception(
            "Persistent logging could not be configured path=%s", LOG_PATH,
        )
        return
    handler._furniture_ar_persistent = True
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
    ))
    root_logger.addHandler(handler)


_configure_persistent_logging()

app = FastAPI(title="TripoSR Product Studio")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
conversion_lock = threading.Lock()
conversion_job_lock = threading.Lock()
dimension_lock = threading.Lock()
save_state_lock = threading.Lock()
conversion_jobs: dict[UUID, dict] = {}
active_saves: set[UUID] = set()
saved_products: dict[UUID, tuple[str, str, dict | None, str | None]] = {}
LOGGER = logging.getLogger("furniture_ar.web")
SAFE_ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PREVIEW_SUFFIXES = {".glb", ".obj", ".usdz", ".png", ".jpg", ".jpeg", ".webp", ".mtl"}
DOWNLOAD_NAMES = {"model.glb", "model.obj", "model.usdz"}
QUALITY_THRESHOLDS = (18.0, 20.0, 22.0)
ERROR_REFERENCE_HEADER = "X-Error-Reference"
ASSET_MEDIA_TYPES = {
    ".glb": "model/gltf-binary",
    ".obj": "text/plain; charset=utf-8",
    ".mtl": "text/plain; charset=utf-8",
    ".usdz": "model/vnd.usdz+zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _record_exception(message: str, exc: Exception, request: Request | None = None) -> str:
    reference = uuid4().hex[:12]
    request_details = ""
    if request is not None:
        request_details = f" method={request.method} path={request.url.path}"
    LOGGER.error(
        "%s error_reference=%s%s",
        message, reference, request_details,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return reference


def _error_headers(reference: str) -> dict[str, str]:
    return {
        ERROR_REFERENCE_HEADER: reference,
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError):
    """Return safe, readable form errors instead of FastAPI's object array."""
    messages = []
    for error in exc.errors():
        location = ".".join(
            str(part) for part in error.get("loc", ())
            if part not in {"body", "query", "path"}
        )
        message = str(error.get("msg") or "Invalid value.")
        messages.append(f"{location}: {message}" if location else message)
    detail = " ".join(messages) or "The submitted request is invalid."
    LOGGER.warning(
        "Request validation failed method=%s path=%s detail=%s",
        request.method, request.url.path, detail,
    )
    return JSONResponse(
        {"detail": detail},
        status_code=422,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.exception_handler(Exception)
async def unhandled_server_error(request: Request, exc: Exception):
    """Return an actionable error while preserving the complete traceback."""
    reference = _record_exception("Unhandled server error", exc, request)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {
                "error": "An unexpected server error occurred.",
                "error_reference": reference,
            },
            status_code=500,
            headers=_error_headers(reference),
        )

    recovery = ""
    conversion_id = getattr(request.state, "conversion_id", None)
    if conversion_id is not None:
        recovery_path = f"/conversions/{conversion_id}"
        recovery = (
            f'<button class="button primary" type="button" '
            f'hx-get="{recovery_path}" hx-target="#conversion-result" '
            f'hx-swap="innerHTML">Recover completed conversion</button>'
        )
    return HTMLResponse(
        (
            '<div class="notice notice-error" role="alert">'
            "<span>An unexpected server error occurred. "
            f"Reference: <code>{reference}</code></span>{recovery}</div>"
        ),
        status_code=500,
        headers=_error_headers(reference),
    )


def _first_forwarded_value(value: str | None) -> str:
    return (value or "").split(",", 1)[0].strip()


def external_base_url(request: Request) -> str:
    """Build public URLs from proxy headers without ever falling back to a path."""
    forwarded = request.headers.get("forwarded", "")
    forwarded_parts = {}
    if forwarded:
        for item in forwarded.split(",", 1)[0].split(";"):
            key, separator, value = item.strip().partition("=")
            if separator:
                forwarded_parts[key.lower()] = value.strip().strip('"')
    scheme = _first_forwarded_value(request.headers.get("x-forwarded-proto"))
    scheme = scheme or forwarded_parts.get("proto") or request.url.scheme
    if scheme not in {"http", "https"}:
        scheme = request.url.scheme if request.url.scheme in {"http", "https"} else "https"
    host = _first_forwarded_value(request.headers.get("x-forwarded-host"))
    host = host or forwarded_parts.get("host") or request.headers.get("host", "")
    if not host or not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", host):
        host = request.url.netloc
    return f"{scheme}://{host}/"


def _external_url(request: Request, path: str) -> str:
    return urljoin(external_base_url(request), path.lstrip("/"))


def _load_candidate_manifest(work_dir: Path) -> dict | None:
    manifest_path = work_dir / "candidate_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        LOGGER.warning("Candidate manifest could not be read path=%s", manifest_path)
        return None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("candidates"), list):
        return None
    return manifest


def _manifest_candidate(work_dir: Path, threshold: float, manifest: dict | None = None) -> tuple[dict, Path]:
    manifest = manifest or _load_candidate_manifest(work_dir)
    if manifest is None:
        raise HTTPException(404, "Quality candidate not found.")
    try:
        entry = next(
            item for item in manifest["candidates"]
            if float(item.get("threshold")) == float(threshold)
        )
        relative = Path(entry["directory"])
    except (StopIteration, KeyError, TypeError, ValueError):
        raise HTTPException(404, "Quality candidate not found.") from None
    root = work_dir.resolve()
    candidate_dir = (root / relative).resolve()
    try:
        candidate_dir.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Unsafe quality candidate path.") from None
    if not candidate_dir.is_dir():
        raise HTTPException(404, "Quality candidate not found.")
    return entry, candidate_dir


def _selected_original_model_dir(work_dir: Path) -> Path:
    manifest = _load_candidate_manifest(work_dir)
    if manifest is None:
        return work_dir
    try:
        selected = float(manifest["selected_threshold"])
        _, candidate_dir = _manifest_candidate(work_dir, selected, manifest)
    except (KeyError, TypeError, ValueError, HTTPException):
        LOGGER.warning("Candidate selection is invalid path=%s", work_dir / "candidate_manifest.json")
        return work_dir
    return candidate_dir


def _source_model_key(work_dir: Path, model_dir: Path | None = None) -> str:
    model_dir = model_dir or _selected_original_model_dir(work_dir)
    try:
        return model_dir.resolve().relative_to(work_dir.resolve()).as_posix() or "."
    except ValueError:
        raise HTTPException(400, "The selected model path is outside this conversion.") from None


def _selected_model_dir(work_dir: Path) -> Path:
    original_dir = _selected_original_model_dir(work_dir)
    state = load_dimension_state(work_dir, _source_model_key(work_dir, original_dir))
    return work_dir / "dimensioned" if state is not None else original_dir


def _resolve_generated_asset(conversion_id: UUID, filename: str, *, download: bool = False) -> Path:
    if not SAFE_ASSET_NAME.fullmatch(filename) or Path(filename).name != filename:
        raise HTTPException(400, "Unsafe model filename.")
    if Path(filename).suffix.lower() not in PREVIEW_SUFFIXES:
        raise HTTPException(404, "Model asset not found.")
    if download and filename not in DOWNLOAD_NAMES:
        raise HTTPException(404, "Download asset not found.")
    work_dir = (GENERATED_DIR / str(conversion_id)).resolve()
    asset_dir = _selected_model_dir(work_dir) if filename in DOWNLOAD_NAMES else work_dir
    path = (asset_dir / filename).resolve()
    if path.parent != asset_dir.resolve():
        raise HTTPException(400, "Unsafe model path.")
    if not path.is_file() or path.stat().st_size <= 0:
        raise HTTPException(404, "Model asset not found.")
    return path


def _resolve_candidate_asset(
    conversion_id: UUID, threshold: float, filename: str, *, download: bool = False,
) -> Path:
    if filename not in DOWNLOAD_NAMES or (download and filename != "model.glb"):
        raise HTTPException(404, "Quality candidate asset not found.")
    work_dir = (GENERATED_DIR / str(conversion_id)).resolve()
    _, candidate_dir = _manifest_candidate(work_dir, threshold)
    path = (candidate_dir / filename).resolve()
    if path.parent != candidate_dir.resolve() or not path.is_file() or path.stat().st_size <= 0:
        raise HTTPException(404, "Quality candidate asset not found.")
    return path


def _asset_metadata(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    size = path.stat().st_size
    value = float(size)
    unit = "bytes"
    for candidate in ("KB", "MB", "GB"):
        if value < 1024 or candidate == "GB":
            break
        value /= 1024
        unit = candidate
    display = f"{int(value)} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
    return {"bytes": size, "display": display}


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/service-worker.js"} or response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"asset_version": ASSET_VERSION},
    )


@app.get("/conversions/{conversion_id}", response_class=HTMLResponse)
def conversion_result(request: Request, conversion_id: UUID):
    """Reopen a completed conversion after a response or browser failure."""
    return templates.TemplateResponse(
        request, "conversion_result.html", _conversion_context(request, conversion_id),
    )


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    source = (BASE_DIR / "static" / "service-worker.js").read_text(encoding="utf-8")
    return Response(
        source.replace("__ASSET_VERSION__", ASSET_VERSION),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    return FileResponse(
        BASE_DIR / "static" / "manifest.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/models/{conversion_id}/preview/{filename}", name="preview_asset")
def preview_asset(request: Request, conversion_id: UUID, filename: str):
    path = _resolve_generated_asset(conversion_id, filename)
    media_type = ASSET_MEDIA_TYPES[path.suffix.lower()]
    LOGGER.info(
        "Serving preview conversion_id=%s asset=%s bytes=%s media_type=%s range=%s host=%s",
        conversion_id, filename, path.stat().st_size, media_type,
        request.headers.get("range", "none"), external_base_url(request),
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        stat_result=path.stat(),
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/models/{conversion_id}/download/{filename}", name="download_asset")
def download_asset(request: Request, conversion_id: UUID, filename: str):
    path = _resolve_generated_asset(conversion_id, filename, download=True)
    media_type = ASSET_MEDIA_TYPES[path.suffix.lower()]
    LOGGER.info(
        "Serving download conversion_id=%s asset=%s bytes=%s host=%s",
        conversion_id, filename, path.stat().st_size, external_base_url(request),
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
        stat_result=path.stat(),
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get(
    "/models/{conversion_id}/candidates/{threshold}/preview/{filename}",
    name="candidate_preview_asset",
)
def candidate_preview_asset(
    request: Request, conversion_id: UUID, threshold: float, filename: str,
):
    path = _resolve_candidate_asset(conversion_id, threshold, filename)
    media_type = ASSET_MEDIA_TYPES[path.suffix.lower()]
    LOGGER.info(
        "Serving candidate preview conversion_id=%s threshold=%s asset=%s bytes=%s",
        conversion_id, threshold, filename, path.stat().st_size,
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        stat_result=path.stat(),
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get(
    "/models/{conversion_id}/candidates/{threshold}/download/model.glb",
    name="candidate_download_asset",
)
def candidate_download_asset(request: Request, conversion_id: UUID, threshold: float):
    path = _resolve_candidate_asset(conversion_id, threshold, "model.glb", download=True)
    return FileResponse(
        path,
        media_type=ASSET_MEDIA_TYPES[".glb"],
        filename=f"model-threshold-{threshold:g}.glb",
        content_disposition_type="attachment",
        stat_result=path.stat(),
        headers={
            "Cache-Control": "private, no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _conversion_context(
    request: Request, conversion_id: UUID, image_path: Path | None = None,
) -> dict:
    work_dir = GENERATED_DIR / str(conversion_id)
    if image_path is None:
        image_path = next(iter(sorted(work_dir.glob("source.*"))), None)
    if image_path is None or not image_path.is_file():
        raise HTTPException(404, "Conversion source image was not found.")

    original_model_dir = _selected_original_model_dir(work_dir)
    source_model_key = _source_model_key(work_dir, original_model_dir)
    dimension_state = load_dimension_state(work_dir, source_model_key)
    model_dir = work_dir / "dimensioned" if dimension_state is not None else original_model_dir
    obj_path = model_dir / "model.obj"
    glb_path = model_dir / "model.glb"
    usdz_path = model_dir / "model.usdz"
    material_report_path = model_dir / "material_report.json"
    material_report = {}
    if material_report_path.is_file():
        try:
            material_report = json.loads(material_report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            material_report = {"material_error": "Material report could not be read."}
    glb_inspection = material_report.get("glb_inspection", {})
    usdz_inspection = material_report.get("usdz_inspection", {})
    glb_valid = bool(glb_path.is_file() and glb_inspection.get("valid"))
    usdz_valid = bool(usdz_path.is_file() and usdz_inspection.get("valid"))
    preview_path = f"/models/{conversion_id}/preview"
    download_path = f"/models/{conversion_id}/download"
    obj_url = _external_url(request, f"{preview_path}/model.obj") if obj_path.is_file() else None
    glb_url = _external_url(request, f"{preview_path}/model.glb") if glb_valid else None
    usdz_url = _external_url(request, f"{preview_path}/model.usdz") if usdz_valid else None

    manifest = _load_candidate_manifest(work_dir)
    quality_candidates = []
    selected_threshold = None
    if manifest is not None:
        try:
            selected_threshold = float(manifest["selected_threshold"])
        except (KeyError, TypeError, ValueError):
            selected_threshold = None
        descriptions = {
            18.0: ("More detail", "Keeps more thin geometry; may include extra surface noise."),
            20.0: ("Balanced", "Recommended balance between thin parts and clean surfaces."),
            22.0: ("Cleaner", "Removes more noise; may trim the thinnest geometry."),
        }
        for item in manifest.get("candidates", []):
            try:
                threshold = float(item["threshold"])
                _, candidate_dir = _manifest_candidate(work_dir, threshold, manifest)
            except (KeyError, TypeError, ValueError, HTTPException):
                continue
            candidate_glb = candidate_dir / "model.glb"
            candidate_report = {}
            try:
                candidate_report = json.loads(
                    (candidate_dir / "material_report.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError, TypeError):
                pass
            if not candidate_glb.is_file() or not candidate_report.get("glb_inspection", {}).get("valid"):
                continue
            threshold_slug = f"{threshold:g}"
            label, description = descriptions.get(
                threshold, (f"Threshold {threshold_slug}", "Alternative geometry extraction."),
            )
            quality_candidates.append({
                "threshold": threshold,
                "threshold_display": threshold_slug,
                "label": label,
                "description": description,
                "selected": selected_threshold == threshold,
                "glb_file": _asset_metadata(candidate_glb),
                "preview_url": _external_url(
                    request,
                    f"/models/{conversion_id}/candidates/{threshold_slug}/preview/model.glb",
                ),
                "download_url": _external_url(
                    request,
                    f"/models/{conversion_id}/candidates/{threshold_slug}/download/model.glb",
                ),
            })

    LOGGER.info(
        "Conversion ready conversion_id=%s public_base=%s selected_threshold=%s glb_valid=%s "
        "glb_bytes=%s obj_bytes=%s usdz_valid=%s usdz_bytes=%s",
        conversion_id, external_base_url(request), selected_threshold, glb_valid,
        glb_path.stat().st_size if glb_path.is_file() else 0,
        obj_path.stat().st_size if obj_path.is_file() else 0,
        usdz_valid, usdz_path.stat().st_size if usdz_path.is_file() else 0,
    )
    return {
        "conversion_id": conversion_id,
        "image_url": _external_url(request, f"{preview_path}/{image_path.name}"),
        "processed_url": _external_url(request, f"{preview_path}/processed.png"),
        "obj_url": obj_url,
        "glb_url": glb_url,
        "usdz_url": usdz_url,
        "obj_download_url": _external_url(request, f"{download_path}/model.obj") if obj_path.is_file() else None,
        "glb_download_url": _external_url(request, f"{download_path}/model.glb") if glb_valid else None,
        "usdz_download_url": _external_url(request, f"{download_path}/model.usdz") if usdz_valid else None,
        "obj_file": _asset_metadata(obj_path),
        "glb_file": _asset_metadata(glb_path) if glb_valid else None,
        "usdz_file": _asset_metadata(usdz_path) if usdz_valid else None,
        "glb_valid": glb_valid,
        "usdz_valid": usdz_valid,
        "material_report": material_report,
        "material_error": material_report.get("material_error"),
        "usdz_error": material_report.get("usdz_error"),
        "fallback_material_applied": material_report.get("fallback_material_applied", False),
        "material_strategy": material_report.get("material_strategy"),
        "original_texture_preserved": material_report.get("original_texture_preserved", False),
        "vertex_colors_preserved": material_report.get("vertex_colors_preserved", False),
        "quality_candidates": quality_candidates,
        "selected_threshold": selected_threshold,
        "dimension_state": dimension_state,
        "dimensions_applied": dimension_state is not None,
    }


def _validate_conversion_options(resolution: int, density_threshold: float) -> None:
    if resolution not in range(32, 321, 32):
        raise HTTPException(400, "Resolution must be between 32 and 320 in steps of 32.")
    if not 10 <= density_threshold <= 40:
        raise HTTPException(400, "Geometry threshold must be between 10 and 40.")


def _update_conversion_job(
    conversion_id: UUID,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error: str | None = None,
    error_reference: str | None = None,
) -> None:
    with conversion_job_lock:
        job = conversion_jobs.get(conversion_id)
        if job is None:
            return
        if status is not None:
            job["status"] = status
        if progress is not None:
            measured = max(0, min(100, int(progress)))
            job["progress"] = max(int(job.get("progress", 0)), measured)
        if message is not None:
            job["message"] = str(message)[:240]
        if error is not None:
            job["error"] = str(error)[:500]
        if error_reference is not None:
            job["error_reference"] = error_reference


def _run_conversion_job(
    conversion_id: UUID,
    image_path: Path,
    *,
    remove_background: bool,
    foreground_ratio: float,
    resolution: int,
    preserve_details: bool,
    density_threshold: float,
    quality_mode: bool,
) -> None:
    work_dir = GENERATED_DIR / str(conversion_id)

    def report(progress: int, message: str) -> None:
        _update_conversion_job(
            conversion_id, status="running", progress=progress, message=message,
        )

    try:
        report(9, "Upload complete. Starting conversion...")
        triposr.convert(
            image_path,
            work_dir,
            remove_bg=remove_background,
            foreground_ratio=max(0.5, min(foreground_ratio, 1.0)),
            resolution=320 if quality_mode else resolution,
            preserve_details=True if quality_mode else preserve_details,
            density_threshold=density_threshold,
            candidate_thresholds=QUALITY_THRESHOLDS if quality_mode else None,
            progress_callback=report,
        )
        _update_conversion_job(
            conversion_id,
            status="complete",
            progress=100,
            message="3D model generated and validated.",
        )
    except Exception as exc:
        reference = _record_exception(
            f"Background 3D conversion failed conversion_id={conversion_id}", exc,
        )
        shutil.rmtree(work_dir, ignore_errors=True)
        _update_conversion_job(
            conversion_id,
            status="failed",
            message="Conversion failed.",
            error=(
                "3D conversion failed. Please check the server log for the technical cause "
                "and try again."
            ),
            error_reference=reference,
        )
    finally:
        conversion_lock.release()


@app.post("/api/conversions", status_code=202)
def start_conversion_job(
    request: Request,
    image: UploadFile = File(...),
    remove_background: bool = Form(True),
    foreground_ratio: float = Form(0.85),
    resolution: int = Form(256),
    preserve_details: bool = Form(False),
    density_threshold: float = Form(20.0),
    quality_mode: bool = Form(False),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "Please upload a valid image.")
    _validate_conversion_options(resolution, density_threshold)
    if not conversion_lock.acquire(blocking=False):
        raise HTTPException(409, "A 3D conversion is already running. Please wait for it to finish.")

    conversion_id = uuid4()
    work_dir = GENERATED_DIR / str(conversion_id)
    try:
        work_dir.mkdir(parents=True)
        suffix = Path(image.filename or "source.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        image_path = work_dir / f"source{suffix}"
        with image_path.open("wb") as destination:
            shutil.copyfileobj(image.file, destination)

        with conversion_job_lock:
            if len(conversion_jobs) >= 50:
                completed = [
                    job_id for job_id, job in conversion_jobs.items()
                    if job.get("status") in {"complete", "failed"}
                ]
                for job_id in completed[: max(1, len(conversion_jobs) - 49)]:
                    conversion_jobs.pop(job_id, None)
            conversion_jobs[conversion_id] = {
                "status": "queued",
                "progress": 8,
                "message": "Upload complete. Queued for conversion...",
                "error": None,
                "error_reference": None,
            }

        worker = threading.Thread(
            target=_run_conversion_job,
            kwargs={
                "conversion_id": conversion_id,
                "image_path": image_path,
                "remove_background": remove_background,
                "foreground_ratio": foreground_ratio,
                "resolution": resolution,
                "preserve_details": preserve_details,
                "density_threshold": density_threshold,
                "quality_mode": quality_mode,
            },
            name=f"conversion-{conversion_id}",
            daemon=True,
        )
        worker.start()
    except Exception as exc:
        conversion_lock.release()
        shutil.rmtree(work_dir, ignore_errors=True)
        with conversion_job_lock:
            conversion_jobs.pop(conversion_id, None)
        reference = _record_exception("Could not start background conversion", exc, request)
        raise HTTPException(
            500, f"Could not start conversion. Reference: {reference}.",
            headers=_error_headers(reference),
        ) from None

    return JSONResponse(
        {
            "conversion_id": str(conversion_id),
            "status_url": f"/api/conversions/{conversion_id}/status",
        },
        status_code=202,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.get("/api/conversions/{conversion_id}/status")
def conversion_job_status(conversion_id: UUID):
    with conversion_job_lock:
        job = conversion_jobs.get(conversion_id)
        if job is None:
            raise HTTPException(404, "Conversion job not found.")
        payload = {
            "conversion_id": str(conversion_id),
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
        }
        if job["status"] == "complete":
            payload["result_url"] = f"/conversions/{conversion_id}"
        if job["status"] == "failed":
            payload["error"] = job.get("error") or "Conversion failed."
            payload["error_reference"] = job.get("error_reference")
    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.post("/convert", response_class=HTMLResponse)
def convert_image(
    request: Request,
    image: UploadFile = File(...),
    remove_background: bool = Form(True),
    foreground_ratio: float = Form(0.85),
    resolution: int = Form(256),
    preserve_details: bool = Form(False),
    density_threshold: float = Form(20.0),
    quality_mode: bool = Form(False),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Please upload a valid image."}, status_code=400,
        )
    _validate_conversion_options(resolution, density_threshold)

    if not conversion_lock.acquire(blocking=False):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "A 3D conversion is already running. Please wait for it to finish."},
            status_code=409,
        )

    try:
        conversion_id = uuid4()
        request.state.conversion_id = conversion_id
        work_dir = GENERATED_DIR / str(conversion_id)
        work_dir.mkdir(parents=True)
        suffix = Path(image.filename or "source.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        image_path = work_dir / f"source{suffix}"
        with image_path.open("wb") as destination:
            shutil.copyfileobj(image.file, destination)

        triposr.convert(
            image_path, work_dir,
            remove_bg=remove_background,
            foreground_ratio=max(0.5, min(foreground_ratio, 1.0)),
            resolution=320 if quality_mode else resolution,
            preserve_details=True if quality_mode else preserve_details,
            density_threshold=density_threshold,
            candidate_thresholds=QUALITY_THRESHOLDS if quality_mode else None,
        )
    except Exception as exc:
        reference = _record_exception("3D conversion failed", exc, request)
        if "work_dir" in locals():
            shutil.rmtree(work_dir, ignore_errors=True)
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {
                "error": "3D conversion failed. Please check the server log for the technical cause and try again.",
                "error_code": "conversion_failed",
                "error_reference": reference,
            }, status_code=500, headers=_error_headers(reference),
        )
    finally:
        conversion_lock.release()
    return templates.TemplateResponse(
        request, "conversion_result.html", _conversion_context(request, conversion_id, image_path),
    )


@app.post("/conversions/{conversion_id}/candidate", response_class=HTMLResponse)
def select_quality_candidate(
    request: Request, conversion_id: UUID, threshold: float = Form(...),
):
    request.state.conversion_id = conversion_id
    work_dir = GENERATED_DIR / str(conversion_id)
    manifest = _load_candidate_manifest(work_dir)
    if manifest is None:
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Quality candidates were not found. Please run the conversion again."},
            status_code=404,
        )
    try:
        entry, candidate_dir = _manifest_candidate(work_dir, threshold, manifest)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "conversion_result.html", {"error": exc.detail}, status_code=exc.status_code,
        )
    try:
        report = json.loads((candidate_dir / "material_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        report = {}
    if not all((candidate_dir / name).is_file() for name in ("model.obj", "model.glb")) \
            or not report.get("glb_inspection", {}).get("valid"):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "That quality candidate is incomplete or failed validation."},
            status_code=409,
        )

    with save_state_lock:
        if conversion_id in active_saves or conversion_id in saved_products:
            return templates.TemplateResponse(
                request, "conversion_result.html",
                {"error": "The selected model cannot be changed during or after saving."},
                status_code=409,
            )
        manifest["selected_threshold"] = float(entry["threshold"])
        temporary = work_dir / "candidate_manifest.tmp"
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temporary.replace(work_dir / "candidate_manifest.json")

    LOGGER.info(
        "Quality candidate selected conversion_id=%s threshold=%s",
        conversion_id, manifest["selected_threshold"],
    )
    return templates.TemplateResponse(
        request, "conversion_result.html", _conversion_context(request, conversion_id),
    )


@app.post("/conversions/{conversion_id}/dimensions", response_class=HTMLResponse)
def update_dimensions(
    request: Request,
    conversion_id: UUID,
    width: str = Form(...),
    height: str = Form(...),
    depth: str = Form(...),
    unit: str = Form(...),
    scaling_mode: str = Form(...),
):
    request.state.conversion_id = conversion_id
    work_dir = GENERATED_DIR / str(conversion_id)
    if not work_dir.is_dir():
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Conversion files were not found."}, status_code=404,
        )
    try:
        requested = normalize_dimensions(width, height, depth, unit, scaling_mode)
    except ValueError as exc:
        context = _conversion_context(request, conversion_id)
        context["dimension_error"] = str(exc)
        return templates.TemplateResponse(
            request, "conversion_result.html", context, status_code=400,
        )

    if not dimension_lock.acquire(blocking=False):
        context = _conversion_context(request, conversion_id)
        context["dimension_error"] = (
            "Another dimensional export is running. Please try again in a moment."
        )
        return templates.TemplateResponse(
            request, "conversion_result.html", context, status_code=409,
        )

    try:
        with save_state_lock:
            if conversion_id in active_saves or conversion_id in saved_products:
                context = _conversion_context(request, conversion_id)
                context["dimension_error"] = (
                    "Dimensions cannot be changed during or after saving this conversion."
                )
                return templates.TemplateResponse(
                    request, "conversion_result.html", context, status_code=409,
                )
        source_dir = _selected_original_model_dir(work_dir)
        source_key = _source_model_key(work_dir, source_dir)
        create_dimensioned_bundle(work_dir, source_dir, source_key, requested)
    except (FileNotFoundError, ValueError) as exc:
        context = _conversion_context(request, conversion_id)
        context["dimension_error"] = str(exc)
        return templates.TemplateResponse(
            request, "conversion_result.html", context, status_code=400,
        )
    except Exception as exc:
        reference = _record_exception(
            f"Dimensional model export failed conversion_id={conversion_id}", exc, request,
        )
        context = _conversion_context(request, conversion_id)
        context["dimension_error"] = (
            "The dimensionally accurate model could not be exported. "
            f"The original generated model is unchanged. Reference: {reference}."
        )
        return templates.TemplateResponse(
            request, "conversion_result.html", context, status_code=500,
            headers=_error_headers(reference),
        )
    finally:
        dimension_lock.release()

    context = _conversion_context(request, conversion_id)
    context["dimension_notice"] = (
        "Dimensions were applied to the GLB, OBJ, and available USDZ exports."
    )
    return templates.TemplateResponse(request, "conversion_result.html", context)


@app.post("/conversions/{conversion_id}/dimensions/reset", response_class=HTMLResponse)
def reset_dimensions(request: Request, conversion_id: UUID):
    request.state.conversion_id = conversion_id
    work_dir = GENERATED_DIR / str(conversion_id)
    if not work_dir.is_dir():
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Conversion files were not found."}, status_code=404,
        )
    with dimension_lock:
        with save_state_lock:
            if conversion_id in active_saves or conversion_id in saved_products:
                context = _conversion_context(request, conversion_id)
                context["dimension_error"] = (
                    "Dimensions cannot be reset during or after saving this conversion."
                )
                return templates.TemplateResponse(
                    request, "conversion_result.html", context, status_code=409,
                )
        reset_dimensioned_bundle(work_dir)
    context = _conversion_context(request, conversion_id)
    context["dimension_notice"] = (
        "Original generated scale restored. Enter real dimensions again before saving or AR."
    )
    return templates.TemplateResponse(request, "conversion_result.html", context)


@app.post("/products", response_class=HTMLResponse)
def create_product(
    request: Request,
    conversion_id: UUID = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    subcategory: str = Form(...),
    description: str = Form(""),
    price: float | None = Form(None),
    table_name: str = Form(...),
    room_width: str | None = Form(None),
    room_length: str | None = Form(None),
    room_height: str | None = Form(None),
    room_unit: str = Form("m"),
    placement_width: str | None = Form(None),
    placement_depth: str | None = Form(None),
):
    try:
        table_name = validate_table_name(table_name)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "save_result.html", {"error": str(exc)}, status_code=400,
        )

    work_dir = GENERATED_DIR / str(conversion_id)
    with dimension_lock:
        original_model_dir = _selected_original_model_dir(work_dir)
        dimension_state = load_dimension_state(
            work_dir, _source_model_key(work_dir, original_model_dir),
        )
        if dimension_state is None:
            return templates.TemplateResponse(
                request, "save_result.html",
                {
                    "error": (
                        "Apply the furniture's real dimensions before saving. "
                        "This prevents an unscaled model from being stored."
                    )
                },
                status_code=400,
            )

        room_dimensions = None
        fit_result = None
        room_values = (room_width, room_length, room_height)
        if any(value not in (None, "") for value in room_values):
            if not all(value not in (None, "") for value in room_values):
                return templates.TemplateResponse(
                    request, "save_result.html",
                    {"error": "Enter room width, length, and height before saving room data."},
                    status_code=400,
                )
            try:
                room_dimensions = normalize_room_dimensions(
                    room_width, room_length, room_height, room_unit,
                    placement_width, placement_depth,
                )
                final = dimension_state["final_dimensions_m"]
                area = room_dimensions.get("placement_area")
                fit_result = check_furniture_fit(
                    (
                        final["width_m"],
                        final["height_m"],
                        final["depth_m"],
                    ),
                    (
                        room_dimensions["width_m"],
                        room_dimensions["length_m"],
                        room_dimensions["height_m"],
                    ),
                    (area["width_m"], area["depth_m"]) if area else None,
                )
            except (KeyError, TypeError, ValueError) as exc:
                return templates.TemplateResponse(
                    request, "save_result.html", {"error": str(exc)}, status_code=400,
                )

        with save_state_lock:
            if conversion_id in active_saves or conversion_id in saved_products:
                return templates.TemplateResponse(
                    request, "save_result.html",
                    {"error": "This conversion has already been saved or is currently saving."},
                    status_code=409,
                )
            active_saves.add(conversion_id)

    model_dir = _selected_model_dir(work_dir)
    images = [*work_dir.glob("source.*")]
    if not images or not (model_dir / "model.obj").is_file() or not (model_dir / "model.glb").is_file():
        with save_state_lock:
            active_saves.discard(conversion_id)
        return templates.TemplateResponse(
            request, "save_result.html", {"error": "Conversion files were not found."},
            status_code=404,
        )
    product = {
        "name": name.strip(),
        "category": category.strip(),
        "subcategory": subcategory.strip(),
        "description": description.strip(),
        "price": price,
        "width": dimension_state["requested"]["width"],
        "height": dimension_state["requested"]["height"],
        "depth": dimension_state["requested"]["depth"],
        "original_unit": dimension_state["requested"]["unit"],
        "width_m": dimension_state["requested"]["width_m"],
        "height_m": dimension_state["requested"]["height_m"],
        "depth_m": dimension_state["requested"]["depth_m"],
        "scaling_mode": dimension_state["requested"]["scaling_mode"],
        "applied_scale_factors": dimension_state["scale_factors"],
        "axis_mapping": dimension_state["axis_mapping"],
        "model_orientation": dimension_state["model_orientation"],
        "final_dimensions_m": dimension_state["final_dimensions_m"],
        "room_dimensions": room_dimensions,
        "fit_result": fit_result,
    }
    try:
        usdz_path = model_dir / "model.usdz"
        outcome = save_product(
            conversion_id=conversion_id,
            product=product,
            image_path=images[0],
            obj_path=model_dir / "model.obj",
            glb_path=model_dir / "model.glb",
            usdz_path=usdz_path if usdz_path.is_file() else None,
            table_name=table_name,
        )
    except SupabaseNotConfigured as exc:
        with save_state_lock:
            active_saves.discard(conversion_id)
        return templates.TemplateResponse(
            request, "save_result.html", {"error": str(exc)}, status_code=503,
        )
    except Exception as exc:
        with save_state_lock:
            active_saves.discard(conversion_id)
        reference = _record_exception(
            f"Supabase save failed conversion_id={conversion_id}", exc, request,
        )
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": f"Supabase save failed. Reference: {reference}."},
            status_code=500, headers=_error_headers(reference),
        )
    saved = outcome.product
    product_id = str(saved.get("id", ""))
    if not product_id:
        with save_state_lock:
            active_saves.discard(conversion_id)
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": "Supabase saved the row but did not return its ID; Undo is unavailable."},
            status_code=502,
        )
    with save_state_lock:
        active_saves.discard(conversion_id)
        saved_products[conversion_id] = (
            table_name, product_id, outcome.previous_product, outcome.new_image_path,
        )
    return templates.TemplateResponse(
        request, "save_result.html",
        {
            "product": saved, "conversion_id": conversion_id, "table_name": table_name,
            "image_reused": outcome.image_reused,
        },
    )


@app.delete("/products/{conversion_id}", response_class=HTMLResponse)
def undo_product(request: Request, conversion_id: UUID):
    with save_state_lock:
        saved = saved_products.get(conversion_id)
    if saved is None:
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": "This save was already undone or is no longer available."},
            status_code=404,
        )

    table_name, product_id, previous_product, new_image_path = saved
    try:
        undo_product_save(
            conversion_id=conversion_id, table_name=table_name, product_id=product_id,
            previous_product=previous_product, new_image_path=new_image_path,
        )
    except Exception as exc:
        reference = _record_exception(
            f"Supabase undo failed conversion_id={conversion_id}", exc, request,
        )
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": f"Undo failed. Reference: {reference}."},
            status_code=500, headers=_error_headers(reference),
        )
    with save_state_lock:
        saved_products.pop(conversion_id, None)
    return templates.TemplateResponse(
        request, "save_result.html",
        {"undone": True, "restored": previous_product is not None},
    )


@app.get("/api/models")
def saved_model_library(request: Request):
    """Return a server-sanitized projection of saved Supabase products."""
    try:
        models = list_models()
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ValueError as exc:
        reference = _record_exception("Model library configuration is invalid", exc, request)
        return JSONResponse(
            {
                "error": "The saved model library is not configured correctly.",
                "error_reference": reference,
            },
            status_code=500,
            headers=_error_headers(reference),
        )
    except Exception as exc:
        reference = _record_exception("Supabase model library request failed", exc, request)
        return JSONResponse(
            {
                "error": "Saved models are temporarily unavailable.",
                "error_reference": reference,
            },
            status_code=502,
            headers=_error_headers(reference),
        )
    return JSONResponse(
        {"models": models, "count": len(models)},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.post("/api/room-captures/validate")
def validate_native_room_capture(capture: RoomPlanCapture):
    """Validate and normalize native RoomPlan data without retaining room scans."""
    return {
        "accepted": True,
        "retained": False,
        "capture": model_payload(capture),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/models/{conversion_id}", include_in_schema=False)
def debug_model(conversion_id: UUID):
    if os.getenv("MODEL_DEBUG", "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(404, "Model diagnostics are disabled.")
    work_dir = GENERATED_DIR / str(conversion_id)
    model_dir = _selected_model_dir(work_dir)
    glb_path = model_dir / "model.glb"
    usdz_path = model_dir / "model.usdz"
    return inspect_model(glb_path, usdz_path if usdz_path.is_file() else None)
