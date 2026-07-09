import shutil
import threading
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from supabase_store import (
    SupabaseNotConfigured, save_product, undo_product_save,
    validate_table_name,
)
from triposr_service import triposr

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="TripoSR Product Studio")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
conversion_lock = threading.Lock()
save_state_lock = threading.Lock()
active_saves: set[UUID] = set()
saved_products: dict[UUID, tuple[str, str, dict | None, str | None]] = {}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        BASE_DIR / "static" / "service-worker.js",
        media_type="application/javascript",
    )


@app.post("/convert", response_class=HTMLResponse)
def convert_image(
    request: Request,
    image: UploadFile = File(...),
    remove_background: bool = Form(True),
    foreground_ratio: float = Form(0.85),
    resolution: int = Form(320),
    preserve_details: bool = Form(False),
    density_threshold: float = Form(20.0),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Please upload a valid image."}, status_code=400,
        )
    if resolution not in range(32, 321, 32):
        raise HTTPException(400, "Resolution must be between 32 and 320 in steps of 32.")
    if not 10 <= density_threshold <= 40:
        raise HTTPException(400, "Geometry threshold must be between 10 and 40.")

    if not conversion_lock.acquire(blocking=False):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "A 3D conversion is already running. Please wait for it to finish."},
            status_code=409,
        )

    try:
        conversion_id = uuid4()
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
            resolution=resolution,
            preserve_details=preserve_details,
            density_threshold=density_threshold,
        )
    except Exception as exc:
        if "work_dir" in locals():
            shutil.rmtree(work_dir, ignore_errors=True)
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": f"3D conversion failed: {exc}"}, status_code=500,
        )
    finally:
        conversion_lock.release()

    base_url = f"/generated/{conversion_id}"
    obj_path = work_dir / "model.obj"
    glb_path = work_dir / "model.glb"
    return templates.TemplateResponse(
        request, "conversion_result.html",
        {
            "conversion_id": conversion_id,
            "image_url": f"{base_url}/{image_path.name}",
            "processed_url": f"{base_url}/processed.png",
            "obj_url": f"{base_url}/model.obj" if obj_path.is_file() else None,
            "glb_url": f"{base_url}/model.glb" if glb_path.is_file() else None,
        },
    )


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
):
    try:
        table_name = validate_table_name(table_name)
    except ValueError as exc:
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

    work_dir = GENERATED_DIR / str(conversion_id)
    images = [*work_dir.glob("source.*")]
    if not images or not (work_dir / "model.obj").is_file() or not (work_dir / "model.glb").is_file():
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
    }
    try:
        outcome = save_product(
            conversion_id=conversion_id,
            product=product,
            image_path=images[0],
            obj_path=work_dir / "model.obj",
            glb_path=work_dir / "model.glb",
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
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": f"Supabase save failed: {exc}"}, status_code=500,
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
        return templates.TemplateResponse(
            request, "save_result.html", {"error": f"Undo failed: {exc}"},
            status_code=500,
        )
    with save_state_lock:
        saved_products.pop(conversion_id, None)
    return templates.TemplateResponse(
        request, "save_result.html",
        {"undone": True, "restored": previous_product is not None},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
