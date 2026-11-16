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
    write_render_status,
)


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

