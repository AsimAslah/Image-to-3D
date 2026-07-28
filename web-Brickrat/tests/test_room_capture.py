import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from room_capture import RoomPlanCapture, model_payload


def capture_payload():
    return {
        "capture_id": "native-capture-1",
        "room_width_m": 4.2,
        "room_length_m": 5.1,
        "room_height_m": 2.7,
        "floor_plane": {
            "position_m": {"x": 0, "y": 0, "z": 0},
            "normal": {"x": 0, "y": 1, "z": 0},
        },
        "walls": [{
            "id": "wall-1",
            "width_m": 4.2,
            "height_m": 2.7,
            "position_m": {"x": 0, "y": 1.35, "z": -2.55},
            "normal": {"x": 0, "y": 0, "z": 1},
        }],
        "openings": [{
            "id": "door-1",
            "kind": "door",
            "width_m": 0.9,
            "height_m": 2.1,
            "position_m": {"x": 1, "y": 1.05, "z": -2.55},
        }],
    }


class RoomCaptureContractTests(unittest.TestCase):
    def test_native_roomplan_contract_preserves_required_geometry(self):
        capture = RoomPlanCapture(**capture_payload())
        payload = model_payload(capture)
        self.assertEqual(payload["source"], "apple_roomplan")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["walls"][0]["width_m"], 4.2)
        self.assertEqual(payload["openings"][0]["kind"], "door")
        self.assertEqual(payload["floor_plane"]["normal"]["y"], 1)

    def test_native_roomplan_contract_rejects_non_positive_dimensions(self):
        payload = capture_payload()
        payload["room_height_m"] = 0
        with self.assertRaises(ValidationError):
            RoomPlanCapture(**payload)


if __name__ == "__main__":
    unittest.main()
