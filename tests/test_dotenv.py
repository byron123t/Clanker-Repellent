import tempfile
import unittest
from pathlib import Path

from clanker_repellent.inference.dotenv import load_dotenv, merged_environment


class DotenvTests(unittest.TestCase):
    def test_loads_comments_exports_and_quoted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# comment\nPLAIN=value\nexport QUOTED='two words'\nEMPTY=\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_dotenv(path),
                {"PLAIN": "value", "QUOTED": "two words", "EMPTY": ""},
            )
            self.assertEqual(load_dotenv(path.with_name("missing")), {})

    def test_explicit_environment_overrides_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("PORT=one\nHOST=local\n", encoding="utf-8")

            merged = merged_environment(
                dotenv_path=path, environ={"PORT": "two"}
            )

            self.assertEqual(merged, {"PORT": "two", "HOST": "local"})

    def test_rejects_malformed_duplicate_or_unterminated_lines(self):
        cases = {
            "expected KEY=VALUE": "INVALID\n",
            "invalid environment name": "BAD-NAME=value\n",
            "duplicate environment name": "NAME=one\nNAME=two\n",
            "unterminated quoted value": "NAME='value\n",
        }
        for message, content in cases.items():
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    load_dotenv(path)


if __name__ == "__main__":
    unittest.main()
