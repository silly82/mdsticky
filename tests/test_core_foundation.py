import tempfile
import unittest
from pathlib import Path

from mdsticky_core import (
    CONFLICT_MARKERS,
    contains_conflict_markers,
    scan_markdown_files,
    three_way_merge,
    unified_diff,
)


class CoreFoundationTests(unittest.TestCase):
    def test_scans_all_markdown_files_but_not_base_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.md").write_text("plain text\n", encoding="utf-8")
            (root / "note.mdsticky-base").write_text("base\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "nested.markdown").write_text("- TODO task\n", encoding="utf-8")

            self.assertEqual(
                scan_markdown_files(root),
                [root / "note.md", root / "sub" / "nested.markdown"],
            )

    def test_detects_all_standard_conflict_marker_lines(self):
        text = "<<<<<<< LOCAL\nours\n=======\ntheirs\n>>>>>>> EXTERNAL\n"
        self.assertTrue(contains_conflict_markers(text))
        self.assertEqual(CONFLICT_MARKERS, ("<<<<<<<", "=======", ">>>>>>>"))

    def test_three_way_merge_combines_changes_on_different_lines(self):
        base = "one\ntwo\nthree\n"
        local = "ONE\ntwo\nthree\n"
        external = "one\ntwo\nTHREE\n"
        result = three_way_merge(base, local, external)
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "ONE\ntwo\nTHREE\n")

    def test_three_way_merge_marks_overlapping_changes(self):
        result = three_way_merge("one\ntwo\n", "one\nLOCAL\n", "one\nEXTERNAL\n")
        self.assertTrue(result.has_conflicts)
        self.assertIn("<<<<<<< LOCAL", result.text)
        self.assertIn("=======", result.text)
        self.assertIn(">>>>>>> EXTERNAL", result.text)

    def test_unified_diff_contains_file_names_and_changed_lines(self):
        diff = unified_diff("one\ntwo\n", "one\nTWO\n", "base.md", "current.md")
        self.assertIn("--- base.md", diff)
        self.assertIn("+++ current.md", diff)
        self.assertIn("-two", diff)
        self.assertIn("+TWO", diff)


if __name__ == "__main__":
    unittest.main()
