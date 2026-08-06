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
    def test_scans_only_markdown_files_starting_with_nd_while_excluding_base_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nd_note.md").write_text("plain text\n", encoding="utf-8")
            (root / "other.md").write_text("not a mdsticky note\n", encoding="utf-8")
            (root / "nd_note.mdsticky-base").write_text("base\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "nd_nested.md").write_text("- TODO task\n", encoding="utf-8")

            self.assertEqual(
                scan_markdown_files(root),
                [root / "nd_note.md", root / "sub" / "nd_nested.md"],
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

    def test_three_way_merge_coalesces_many_overlaps_into_one_conflict(self):
        base = "b1\nb2\nb3\nb4\n"
        local = "L1\nb2\nL3\nb4\n"
        external = "E1\nE2\nE3\nE4\n"
        result = three_way_merge(base, local, external)
        self.assertTrue(result.has_conflicts)
        self.assertEqual(result.text.count("<<<<<<< LOCAL"), 1)
        self.assertEqual(result.text.count(">>>>>>> EXTERNAL"), 1)
        self.assertIn("L1\nb2\nL3\nb4\n", result.text)
        self.assertIn("E1\nE2\nE3\nE4\n", result.text)

    def test_three_way_merge_marks_insertion_at_replacement_boundary_as_conflict(self):
        base = "one\ntwo\nthree\n"
        local = "one\nLOCAL\ntwo\nthree\n"
        external = "one\nEXTERNAL\nTHREE\n"
        result = three_way_merge(base, local, external)
        self.assertTrue(result.has_conflicts)

    def test_unified_diff_contains_file_names_and_changed_lines(self):
        diff = unified_diff("one\ntwo\n", "one\nTWO\n", "base.md", "current.md")
        self.assertIn("--- base.md", diff)
        self.assertIn("+++ current.md", diff)
        self.assertIn("-two", diff)
        self.assertIn("+TWO", diff)


if __name__ == "__main__":
    unittest.main()
