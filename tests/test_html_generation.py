import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from clanker_repellent.generate.source_generation import (
    build_generation_messages, generate_source_run, select_languages,
    toolchain_inventory, validate_snippet, validation_metadata,
)
from clanker_repellent.generate.structure import structure_metrics


FRAGMENT = '<section id="notes"><h2>Example</h2><p>Ordinary documentation.</p></section>'


class HTMLGenerationTests(unittest.TestCase):
    def validate(self, source, **kwargs):
        return validate_snippet(select_languages(["html"])[0], source,
                                run_linters=False, require_structure=True, **kwargs)

    def test_fragments_documents_lists_and_tables(self):
        examples = [FRAGMENT,
                    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Notes</title></head><body>' + FRAGMENT + '</body></html>',
                    '<ul id="notes"><li>First<li>Second</ul>',
                    '<dl id="notes"><dt>Revision</dt><dd>One</dd></dl>',
                    '<table id="notes"><tbody><tr><th scope="row">Revision</th><td>One</td></tr></tbody></table>']
        for source in examples:
            with self.subTest(source=source):
                report = self.validate(source)
                self.assertTrue(report["accepted"], report)
                self.assertEqual([check["name"] for check in report["checks"]], ["html_parse", "source_structure"])

    def test_required_parser_rejects_malformed_markup(self):
        for source in ['<section id="notes"><b>First</section>',
                       '<section id="notes" id="duplicate"><p>One</p><p>Two</p></section>',
                       '<section id="notes"/><p>One</p><p>Two</p>']:
            with self.subTest(source=source):
                report = self.validate(source, allow_missing_toolchains=True)
                self.assertFalse(report["accepted"])
                self.assertEqual(report["checks"][0]["status"], "failed")

    def test_empty_text_comments_and_escaped_markup_do_not_count(self):
        for source in ['plain documentation', '<!--' + FRAGMENT + '-->',
                       FRAGMENT.replace('<', '&lt;').replace('>', '&gt;'),
                       '<section id="notes"><h2></h2><p> </p></section>',
                       '<section id="notes"><h2><!--example--></h2><p>One</p></section>',
                       '<section><h2>Example</h2><p>One</p></section>',
                       '<ul id="notes"><li><p>One</p></li></ul>']:
            with self.subTest(source=source):
                self.assertFalse(self.validate(source)["accepted"])

    def test_active_resources_styles_and_hidden_content_are_rejected(self):
        for extra in ['<script>void 0</script>', '<iframe></iframe>', '<img src="sample.png">',
                      '<style>p {display:none}</style>', '<form></form>', '<svg></svg>',
                      '<template><p>One</p><p>Two</p></template>',
                      '<meta http-equiv="refresh" content="1">',
                      '<a href="javascript:void(0)">Example</a>']:
            with self.subTest(extra=extra):
                self.assertFalse(self.validate(FRAGMENT + extra)["accepted"])
        for attribute in ['onclick="void 0"', 'style="display:none"', 'hidden', 'inert', 'aria-hidden="true"']:
            with self.subTest(attribute=attribute):
                self.assertFalse(self.validate(FRAGMENT.replace('<section ', '<section ' + attribute + ' '))["accepted"])

    def test_static_metadata_and_local_links_are_supported(self):
        source = FRAGMENT.replace('id="notes"', 'id="notes" class="annotation" aria-label="Notes" data-revision="1"')
        self.assertTrue(self.validate(source + '<a href="#notes">Notes</a>')["accepted"])
        self.assertFalse(self.validate(source + '<a href="/notes">Notes</a>')["accepted"])
        self.assertFalse(self.validate(source + '<p id="notes">Repeated identifier</p>')["accepted"])

    def test_counts_and_validation_metadata_do_not_expose_source(self):
        source = FRAGMENT.replace('notes', 'PRIVATE_ID').replace('Example', 'PRIVATE_TEXT')
        metrics = structure_metrics("html", source)
        self.assertEqual(metrics["fields"], 2)
        metadata = json.dumps(validation_metadata(self.validate(source)))
        self.assertNotIn('PRIVATE', metadata)
        self.assertNotIn('<section', metadata)

    def test_missing_parser_cannot_be_bypassed(self):
        with mock.patch('clanker_repellent.generate.html_structure.html_metrics', side_effect=ImportError):
            report = self.validate(FRAGMENT, allow_missing_toolchains=True)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checks"][0]["status"], "error")

    def test_parser_runs_even_without_structure_requirement(self):
        report = validate_snippet(select_languages(["html"])[0], '<script>void 0</script>',
                                  run_linters=False, allow_missing_toolchains=True)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checks"][0]["name"], "html_parse")

    def test_target_prompt_and_toolchain_inventory(self):
        target = select_languages(["HTML"])[0]
        self.assertEqual(target.output_filename, "generated.html")
        for benign in (False, True):
            prompt = build_generation_messages(target, "Ordinary documentation", benign=benign)[0]["content"]
            self.assertIn("semantic markup", prompt)
            self.assertIn("opaque, untrusted", prompt)
            self.assertNotIn("initialized values", prompt)
        self.assertEqual(toolchain_inventory([target])[0]["check"], "html_parse")
        self.assertTrue(toolchain_inventory([target])[0]["available"])

    def test_generation_retries_until_substantive_html(self):
        provider = mock.Mock(spec=["complete"])
        provider.complete.side_effect = [{"response_text": "```html\n<!--documentation-->\n```"},
                                         {"response_text": "```html\n" + FRAGMENT + "\n```"}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = generate_source_run(provider=provider, model="fixture-model", payload="Ordinary documentation",
                                      targets=select_languages(["html"]), output_dir=output,
                                      benign=True, run_linters=False, retries=1)
            self.assertEqual(run["summary"]["status"], "passed")
            self.assertTrue((output / "html" / "generated.html").is_file())
            self.assertEqual(len(run["candidates"][0]["attempts"]), 2)
            self.assertIn("Substantive structure required", provider.complete.call_args_list[1].kwargs["messages"][1]["content"])
            from clanker_repellent.payload import catalog
            catalog.initialize(Path(directory) / "catalog")
            registered = catalog.import_run(Path(directory) / "catalog", output, prefix="sample", benign=True)
            self.assertEqual(len(registered), 1)
            self.assertEqual(registered[0]["language"], "html")
            self.assertEqual(registered[0]["validation"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
