import tempfile
import unicodedata
import unittest
from pathlib import Path

from openpyxl import Workbook

from scripts.sync_specs import build_api_spec, cell, newest


class NewestTest(unittest.TestCase):
    def test_finds_xlsx_whose_hangul_name_is_decomposed_by_macos(self):
        # 맥 Finder·브라우저는 한글 파일 이름을 자모가 분리된 NFD 로 저장한다
        with tempfile.TemporaryDirectory() as folder:
            saved = Path(folder) / unicodedata.normalize("NFD", "당고킬러_테이블명세서.xlsx")
            saved.touch()
            self.assertEqual(newest(Path(folder), "당고킬러_테이블명세서"), saved)


class CellTest(unittest.TestCase):
    def test_escapes_tildes_so_ranges_do_not_render_as_strikethrough(self):
        # GitHub 은 한 줄의 물결표 두 개 사이를 취소선으로 그린다
        self.assertEqual(
            cell("외식 빈도 1~7 (1 거의 매일 ~ 7 거의 안 함)"), "외식 빈도 1\\~7 (1 거의 매일 \\~ 7 거의 안 함)"
        )


class ApiSpecTest(unittest.TestCase):
    def test_trailing_empty_columns_are_not_rendered_as_table_columns(self):
        # xlsx 를 시트로 가져오면 서식만 남은 빈 칸이 Z열까지 따라온다
        wb = Workbook()
        ws = wb.active
        ws.title = "공통 규칙"
        for row in (["API 명세 — 공통 규칙"], ["작성 2026-10-27"], ["구분", "항목", "내용"], ["인증", "방식", "JWT"]):
            ws.append(row)
        ws.cell(row=4, column=26).value = ""

        text = build_api_spec(wb, "2026-10-27")

        self.assertIn("| 구분 | 항목 | 내용 |\n| --- | --- | --- |\n| 인증 | 방식 | JWT |", text)


if __name__ == "__main__":
    unittest.main()
