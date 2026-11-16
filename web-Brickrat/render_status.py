"""Minimal persistent status records for the RenderPulse read-only API."""

from __future__ import annotations

import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID

STATUS_FILENAME = "render-status.json"
RENDER_ID_PATTERN = re.compile(r"^R[A-Z0-9]{4,31}$")
VALID_STATES = {"queued", "processing", "completed", "failed"}
SUPABASE_TABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass
class RenderStatusAuthError(RuntimeError):
    status_code: int
    public_message: str


def public_render_id(conversion_id: UUID) -> str:
    """Return the stable public ID without exposing the internal UUID."""
    return f"R{conversion_id.hex[:12].upper()}"


def write_render_status(
    generated_dir: Path,
    conversion_id: UUID,
    status: str,
    *,
    model_format: str | None = None,
) -> dict:
    if status not in VALID_STATES:
        raise ValueError("Unsupported render status.")
    record = {
        "render_id": public_render_id(conversion_id),
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if model_format is not None:
        normalized_format = model_format.upper()
        if not re.fullmatch(r"[A-Z0-9]{2,12}", normalized_format):
            raise ValueError("Invalid model format.")
        record["model_format"] = normalized_format

    work_dir = generated_dir / str(conversion_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    destination = work_dir / STATUS_FILENAME
    temporary = work_dir / f"{STATUS_FILENAME}.tmp"
    temporary.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)
    return record


def read_render_status(generated_dir: Path, render_id: str) -> dict | None:
    normalized = render_id.strip().upper()
    if not RENDER_ID_PATTERN.fullmatch(normalized):
        return None
    for status_path in generated_dir.glob(f"*/{STATUS_FILENAME}"):
        try:
            record = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("render_id") != normalized or record.get("status") not in VALID_STATES:
            continue
        updated_at = record.get("updated_at")
        try:
            datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        result = {
            "render_id": normalized,
            "status": record["status"],
            "updated_at": updated_at,
        }
        model_format = record.get("model_format")
        if isinstance(model_format, str) and re.fullmatch(r"[A-Z0-9]{2,12}", model_format):
            result["model_format"] = model_format
        return result
    return None


def sync_render_status(
    record: dict,
    *,
    client_factory: Callable | None = None,
) -> bool:
    """Upsert a public-safe status record when Supabase sync is configured."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("RENDER_STATUS_SUPABASE_KEY", "").strip()
    if not supabase_url or not supabase_key:
        return False

    table_name = os.getenv("RENDER_STATUS_SUPABASE_TABLE", "render_jobs").strip()
    if not SUPABASE_TABLE_PATTERN.fullmatch(table_name):
        raise ValueError("Invalid render status table name.")

    render_id = str(record.get("render_id", "")).strip().upper()
    status = record.get("status")
    updated_at = str(record.get("updated_at", ""))
    if not RENDER_ID_PATTERN.fullmatch(render_id) or status not in VALID_STATES:
        raise ValueError("Invalid render status record.")
    try:
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid render status timestamp.") from exc

    safe_record = {
        "render_id": render_id,
        "status": status,
        "updated_at": updated_at,
    }
    model_format = record.get("model_format")
    if model_format is not None:
        normalized_format = str(model_format).upper()
        if not re.fullmatch(r"[A-Z0-9]{2,12}", normalized_format):
            raise ValueError("Invalid model format.")
        safe_record["model_format"] = normalized_format

    if client_factory is None:
        from supabase import create_client

        client_factory = create_client
    client = client_factory(supabase_url, supabase_key)
    client.table(table_name).upsert(
        safe_record, on_conflict="render_id",
    ).execute()
    return True


def authorize_status_request(
    authorization: str | None,
    team_id: str | None,
    channel_id: str | None,
) -> None:
    expected_key = os.getenv("RENDER_STATUS_API_KEY", "")
    expected_team = os.getenv("RENDER_STATUS_ALLOWED_TEAM_ID", "")
    allowed_channels = {
        item.strip() for item in os.getenv("RENDER_STATUS_ALLOWED_CHANNEL_IDS", "").split(",")
        if item.strip()
    }
    if not expected_key or not expected_team or not allowed_channels:
        raise RenderStatusAuthError(503, "Render status API is not configured.")

    supplied_key = ""
    if authorization and authorization.startswith("Bearer "):
        supplied_key = authorization.removeprefix("Bearer ")
    if not supplied_key or not hmac.compare_digest(supplied_key, expected_key):
        raise RenderStatusAuthError(401, "Invalid API credentials.")
    if not team_id or not hmac.compare_digest(team_id, expected_team):
        raise RenderStatusAuthError(403, "Render status access is not allowed.")
    if channel_id not in allowed_channels:
        raise RenderStatusAuthError(403, "Render status access is not allowed.")

