import os
from pathlib import Path
from uuid import UUID


class SupabaseNotConfigured(RuntimeError):
    pass


def save_product(*, conversion_id: UUID, product: dict, image_path: Path,
                 obj_path: Path, glb_path: Path) -> dict:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise SupabaseNotConfigured(
            "Set SUPABASE_URL and SUPABASE_KEY before saving products."
        )

    from supabase import create_client

    client = create_client(url, key)
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "products")
    prefix = str(conversion_id)

    def upload(path: Path, remote_name: str, content_type: str) -> str:
        remote_path = f"{prefix}/{remote_name}"
        with path.open("rb") as file:
            client.storage.from_(bucket).upload(
                remote_path,
                file,
                {"content-type": content_type, "upsert": True},
            )
        return client.storage.from_(bucket).get_public_url(remote_path)

    image_types = {".png": "image/png", ".webp": "image/webp"}
    image_url = upload(
        image_path,
        f"source{image_path.suffix.lower()}",
        image_types.get(image_path.suffix.lower(), "image/jpeg"),
    )
    obj_url = upload(obj_path, "model.obj", "text/plain")
    glb_url = upload(glb_path, "model.glb", "model/gltf-binary")
    row = {
        **product,
        "image_url": image_url,
        "obj_url": obj_url,
        "model_url": glb_url,
    }
    table = os.getenv("SUPABASE_PRODUCTS_TABLE", "products")
    result = client.table(table).insert(row).execute()
    return result.data[0] if result.data else row
