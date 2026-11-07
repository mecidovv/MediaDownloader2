import os
import unittest

from backend import clipboard


class ClipboardTests(unittest.TestCase):
    def test_read_text_returns_bounded_string(self) -> None:
        text = clipboard.read_text()
        self.assertIsInstance(text, str)
        self.assertLessEqual(len(text), clipboard.MAX_LENGTH)

    @unittest.skipIf(os.name == "nt", "Non-Windows fallback only")
    def test_non_windows_returns_empty_text(self) -> None:
        self.assertEqual(clipboard.read_text(), "")


if __name__ == "__main__":
    unittest.main()
