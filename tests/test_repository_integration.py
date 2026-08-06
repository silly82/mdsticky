import tempfile
import unittest
from pathlib import Path

from mdsticky_core import (
    base_path_for,
    contains_conflict_markers,
    load_text,
    save_with_merge,
    scan_markdown_files,
)


class RepositoryIntegrationTests(unittest.TestCase):
    def test_base_path_is_next_to_markdown_file(self):
        self.assertEqual(
            base_path_for(Path("project.md")),
            Path("project.md.mdsticky-base"),
        )

    def test_markdown_rule_is_not_a_conflict(self):
        self.assertFalse(contains_conflict_markers("=======\n"))

    def test_markdown_and_markdown_extension_get_distinct_bases(self):
        self.assertNotEqual(base_path_for("note.md"), base_path_for("note.markdown"))

    def test_scanned_paths_can_be_used_as_json_object_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "nd_test.md"
            note.write_text("text\n", encoding="utf-8")
            scanned = scan_markdown_files(root)
            self.assertTrue(all(isinstance(path, Path) for path in scanned))
            self.assertTrue(all(isinstance(str(path), str) for path in scanned))

    def test_save_with_merge_creates_base_and_keeps_external_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("one\ntwo\n", encoding="utf-8")
            base = load_text(note)
            note.write_text("one\nEXTERNAL\n", encoding="utf-8")

            result = save_with_merge(note, base, "LOCAL\ntwo\n")

            self.assertFalse(result.has_conflicts)
            self.assertEqual(note.read_text(encoding="utf-8"), "LOCAL\nEXTERNAL\n")
            self.assertEqual((Path(tmp) / "note.md.mdsticky-base").read_text(encoding="utf-8"), "LOCAL\nEXTERNAL\n")

    def test_save_with_merge_writes_markers_and_reports_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("one\ntwo\n", encoding="utf-8")
            base = load_text(note)
            note.write_text("one\nEXTERNAL\n", encoding="utf-8")

            result = save_with_merge(note, base, "one\nLOCAL\n")

            self.assertTrue(result.has_conflicts)
            self.assertTrue(contains_conflict_markers(note.read_text(encoding="utf-8")))
            self.assertFalse((Path(tmp) / "note.md.mdsticky-base").exists())


if __name__ == "__main__":
    unittest.main()
