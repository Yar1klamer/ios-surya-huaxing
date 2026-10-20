"""Reject unverified controller firmware before building a phone payload."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import surya_touch_firmware as fw

class TouchFirmwareTests(unittest.TestCase):
    def test_rejects_missing_and_truncated_images(self):
        for data in (b'', bytes(fw.SIZE - 1), bytes(fw.SIZE + 1)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                fw.validate(data)

    def test_rejects_wrong_image_of_correct_size(self):
        with self.assertRaises(ValueError):
            fw.validate(bytes(fw.SIZE))
