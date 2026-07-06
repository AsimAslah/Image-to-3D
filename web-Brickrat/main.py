import shutil
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from supabase_store import SupabaseNotConfigured, save_product
from triposr_service import triposr

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="TripoSR Product Studio")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/convert", response_class=HTMLResponse)
def convert_image(
    request: Request,
    image: UploadFile = File(...),
    remove_background: bool = Form(False),
    foreground_ratio: float = Form(0.85),
    resolution: int = Form(256),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": "Please upload a valid image."}, status_code=400,
        )
    if resolution not in range(32, 321, 32):
        raise HTTPException(400, "Resolution must be between 32 and 320 in steps of 32.")

    conversion_id = uuid4()
    work_dir = GENERATED_DIR / str(conversion_id)
    work_dir.mkdir(parents=True)
    suffix = Path(image.filename or "source.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    image_path = work_dir / f"source{suffix}"
    with image_path.open("wb") as destination:
        shutil.copyfileobj(image.file, destination)

    try:
        triposr.convert(
            image_path, work_dir,
            remove_bg=remove_background,
            foreground_ratio=max(0.5, min(foreground_ratio, 1.0)),
            resolution=resolution,
        )
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        return templates.TemplateResponse(
            request, "conversion_result.html",
            {"error": f"3D conversion failed: {exc}"}, status_code=500,
        )

    base_url = f"/generated/{conversion_id}"
    return templates.TemplateResponse(
        request, "conversion_result.html",
        {
            "conversion_id": conversion_id,
            "image_url": f"{base_url}/{image_path.name}",
            "obj_url": f"{base_url}/model.obj",
            "glb_url": f"{base_url}/model.glb",
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
):
    work_dir = GENERATED_DIR / str(conversion_id)
    images = [*work_dir.glob("source.*")]
    if not images or not (work_dir / "model.obj").is_file() or not (work_dir / "model.glb").is_file():
        raise HTTPException(404, "Conversion files were not found.")
    product = {
        "name": name.strip(),
        "category": category.strip(),
        "subcategory": subcategory.strip(),
        "description": description.strip(),
        "price": price,
    }
    try:
        saved = save_product(
            conversion_id=conversion_id,
            product=product,
            image_path=images[0],
            obj_path=work_dir / "model.obj",
            glb_path=work_dir / "model.glb",
        )
    except SupabaseNotConfigured as exc:
        return templates.TemplateResponse(
            request, "save_result.html", {"error": str(exc)}, status_code=503,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request, "save_result.html",
            {"error": f"Supabase save failed: {exc}"}, status_code=500,
        )
    return templates.TemplateResponse(request, "save_result.html", {"product": saved})


@app.get("/health")
def health():
    return {"status": "ok"}
