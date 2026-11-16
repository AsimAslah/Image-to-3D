import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from render_status import (
    RenderStatusAuthError,
    authorize_status_request,
    public_render_id,
    read_render_status,
    sync_render_status,
    write_render_status,
)


class FakeQuery:
    def __init__(self):
        self.record = None
        self.on_conflict = None
        self.executed = False

    def upsert(self, record, *, on_conflict):
        self.record = record
        self.on_conflict = on_conflict
        return self

    def execute(self):
        self.executed = True


class FakeSupabase:
    def __init__(self):
        self.table_name = None
        self.query = FakeQuery()

    def table(self, table_name):
        self.table_name = table_name
        return self.query


class RenderStatusTests(unittest.TestCase):
    def test_real_status_transitions_are_persisted_without_fake_progress(self):
        conversion_id = UUID("12345678-1234-5678-1234-567812345678")
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            for state in ("queued", "processing", "completed"):
                record = write_render_status(
                    generated, conversion_id, state,
                    model_format="GLB" if state == "completed" else None,
                )
                self.assertEqual(record["status"], state)
                self.assertNotIn("progress", record)
            saved = read_render_status(generated, public_render_id(conversion_id))
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["model_format"], "GLB")

    def test_unknown_and_invalid_ids_are_not_found(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            self.assertIsNone(read_render_status(generated, "../../secret"))
            self.assertIsNone(read_render_status(generated, "R9999"))

    @patch.dict(os.environ, {}, clear=True)
    def test_supabase_sync_is_optional(self):
        factory_called = False

        def factory(_url, _key):
            nonlocal factory_called
            factory_called = True

        self.assertFalse(sync_render_status({}, client_factory=factory))
        self.assertFalse(factory_called)

    @patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.supabase.co",
        "RENDER_STATUS_SUPABASE_KEY": "server-secret",
        "RENDER_STATUS_SUPABASE_TABLE": "render_jobs",
    }, clear=True)
    def test_supabase_sync_upserts_only_public_safe_fields(self):
        fake = FakeSupabase()
        credentials = []

        def factory(url, key):
            credentials.append((url, key))
            return fake

        synced = sync_render_status({
            "render_id": "R123456789ABC",
            "status": "completed",
            "model_format": "glb",
            "updated_at": "2026-11-17T10:30:00Z",
            "model_url": "https://should-not-leak.example/model.glb",
        }, client_factory=factory)

        self.assertTrue(synced)
        self.assertEqual(credentials, [("https://example.supabase.co", "server-secret")])
        self.assertEqual(fake.table_name, "render_jobs")
        self.assertEqual(fake.query.on_conflict, "render_id")
        self.assertTrue(fake.query.executed)
        self.assertEqual(fake.query.record, {
            "render_id": "R123456789ABC",
            "status": "completed",
            "model_format": "GLB",
            "updated_at": "2026-11-17T10:30:00Z",
        })

    @patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.supabase.co",
        "RENDER_STATUS_SUPABASE_KEY": "server-secret",
        "RENDER_STATUS_SUPABASE_TABLE": "render_jobs; drop table products",
    }, clear=True)
    def test_supabase_sync_rejects_invalid_table_name(self):
        with self.assertRaisesRegex(ValueError, "Invalid render status table"):
            sync_render_status({})

    @patch.dict(os.environ, {
        "RENDER_STATUS_API_KEY": "backend-secret",
        "RENDER_STATUS_ALLOWED_TEAM_ID": "T123",
        "RENDER_STATUS_ALLOWED_CHANNEL_IDS": "C123,C456",
    }, clear=False)
    def test_access_requires_key_workspace_and_channel(self):
        authorize_status_request("Bearer backend-secret", "T123", "C123")
        for args, expected_status in [
            (("Bearer wrong", "T123", "C123"), 401),
            (("Bearer backend-secret", "T999", "C123"), 403),
            (("Bearer backend-secret", "T123", "C999"), 403),
        ]:
            with self.assertRaises(RenderStatusAuthError) as raised:
                authorize_status_request(*args)
            self.assertEqual(raised.exception.status_code, expected_status)


if __name__ == "__main__":
    unittest.main()

