import unittest

from scripts.ci.check_root_files import tracked_paths, unexpected_root_entries


class UnexpectedRootEntriesTest(unittest.TestCase):
    def test_reports_file_added_at_root_outside_allowlist(self):
        self.assertEqual(unexpected_root_entries(["notes.md", "app/main.py", "README.md"]), ["notes.md"])

    def test_files_inside_allowed_folders_pass(self):
        self.assertEqual(unexpected_root_entries(["docs/SYSTEM_DESIGN.md", "frontend/v5/app.mjs", "uv.lock"]), [])

    def test_reports_new_top_level_folder_once(self):
        self.assertEqual(unexpected_root_entries(["misc/a.txt", "misc/b.txt"]), ["misc/"])

    def test_current_repository_root_has_only_allowed_entries(self):
        # 지금 저장소의 루트가 허용 목록과 어긋나면 여기서 먼저 깨진다
        self.assertEqual(unexpected_root_entries(tracked_paths()), [])


if __name__ == "__main__":
    unittest.main()
