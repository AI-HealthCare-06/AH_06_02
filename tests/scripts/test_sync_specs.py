import tempfile
import unicodedata
import unittest
from pathlib import Path

from scripts.sync_specs import newest


class NewestTest(unittest.TestCase):
    def test_finds_xlsx_whose_hangul_name_is_decomposed_by_macos(self):
        # 맥 Finder·브라우저는 한글 파일 이름을 자모가 분리된 NFD 로 저장한다
        with tempfile.TemporaryDirectory() as folder:
            saved = Path(folder) / unicodedata.normalize("NFD", "당고킬러_테이블명세서.xlsx")
            saved.touch()
            self.assertEqual(newest(Path(folder), "당고킬러_테이블명세서"), saved)


if __name__ == "__main__":
    unittest.main()
