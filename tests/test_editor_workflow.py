import tempfile
import unittest
from pathlib import Path

from mdsticky_core import base_path_for, load_text, save_with_merge


class EditorWorkflowTests(unittest.TestCase):
    def test_editor_save_merges_external_change_and_updates_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "nd_test.md"
            note.write_text("# Note\n\n- TODO one\n- TODO two\n", encoding="utf-8")
            base = load_text(note)
            note.write_text("# Note\n\n- TODO one\n- TODO TWO\n", encoding="utf-8")
            local = "# Note\n\n- DONE one\n- TODO two\n"

            result = save_with_merge(note, base, local)

            self.assertFalse(result.has_conflicts)
            self.assertIn("DONE one", note.read_text(encoding="utf-8"))
            self.assertIn("TODO TWO", note.read_text(encoding="utf-8"))
            self.assertEqual(load_text(base_path_for(note)), load_text(note))

    def test_editor_save_keeps_conflict_for_manual_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "nd_test.md"
            note.write_text("- TODO one\n", encoding="utf-8")
            base = load_text(note)
            note.write_text("- TODO external\n", encoding="utf-8")

            result = save_with_merge(note, base, "- TODO local\n")

            self.assertTrue(result.has_conflicts)
            self.assertIn("<<<<<<< LOCAL", load_text(note))
            self.assertFalse(base_path_for(note).exists())


if __name__ == "__main__":
    unittest.main()
