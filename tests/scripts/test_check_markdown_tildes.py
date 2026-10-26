import unittest

from scripts.ci.check_markdown_tildes import unescaped_tilde_lines


class UnescapedTildeLinesTest(unittest.TestCase):
    def test_reports_range_written_with_bare_tilde(self):
        self.assertEqual(unescaped_tilde_lines("위협도 0~100\n"), [1])

    def test_allows_escaped_tilde_inline_code_and_fenced_code(self):
        text = "위협도 0\\~100\n경로는 `~/deploy.log`\n```\ncd ~/project\n```\n"
        self.assertEqual(unescaped_tilde_lines(text), [])

    def test_reports_each_line_once_in_order(self):
        self.assertEqual(unescaped_tilde_lines("1~7\n괜찮음\n2~3 · 4~5\n"), [1, 3])


if __name__ == "__main__":
    unittest.main()
