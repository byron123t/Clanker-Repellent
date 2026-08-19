import io
import unittest
from contextlib import redirect_stdout

from llmddos.generate_cli import build_parser, main


class GenerateCliTests(unittest.TestCase):
    def test_help_uses_server_model_discovery(self):
        help_text = build_parser().format_help()

        self.assertIn("discovered from the server", help_text)
        self.assertIn("--harness {direct,opencode}", help_text)
        self.assertIn("--benign", help_text)
        self.assertNotIn("--model", help_text)

    def test_opencode_harness_options_parse_without_a_model(self):
        defaults = build_parser().parse_args(["--harness", "opencode"])
        args = build_parser().parse_args(
            ["--harness", "opencode", "--opencode-timeout", "45"]
        )

        self.assertEqual(defaults.opencode_timeout, 900.0)
        self.assertEqual(args.harness, "opencode")
        self.assertEqual(args.opencode_timeout, 45.0)
        self.assertFalse(hasattr(args, "model"))

    def test_benign_mode_parses_as_a_generation_control(self):
        args = build_parser().parse_args(["--benign"])

        self.assertTrue(args.benign)

    def test_lists_languages_without_loading_endpoint_configuration(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(["--list-languages"])

        self.assertEqual(status, 0)
        languages = output.getvalue().splitlines()
        self.assertEqual(len(languages), 11)
        self.assertIn("python\tgenerated.py", languages)

    def test_lists_toolchains_without_a_payload(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(["--list-toolchains", "--language", "python"])

        self.assertEqual(status, 0)
        self.assertIn("python_ast\tparser\trequired", output.getvalue())

    def test_payload_is_required_for_generation(self):
        output = io.StringIO()

        with redirect_stdout(output):
            status = main([])

        self.assertEqual(status, 2)
        self.assertIn("--payload is required", output.getvalue())


if __name__ == "__main__":
    unittest.main()
