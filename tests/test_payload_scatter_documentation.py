import unittest
from pathlib import Path

from clanker_repellent.payload.payload_scatter import HUB_CARRIER, STRATEGIES


ROOT = Path(__file__).resolve().parents[1]


class PayloadScatterDocumentationTests(unittest.TestCase):
    def test_every_strategy_requirement_is_documented(self):
        raw_documentation = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("README.md", "EVALUATION.md")
        )
        documentation = " ".join(raw_documentation.split())
        required_concepts = {
            "deterministic selection": "SHA-256(seed + NUL + relative_path)",
            "eligibility exclusions": "Non-UTF-8 or NUL-containing files",
            "replicated topology": "complete assigned payload at each requested position",
            "fragment reconstruction": "reconstructs the original payload exactly",
            "fragmented full copy": "complete replica plus line-chunked inline copies",
            "fragment scaling": "ceil(source physical lines / --inline-source-lines)",
            "multi-payload pool": "--payload-count",
            "required payload schema": "payloads/header.txt",
            "hub line chunks": "split only at physical line boundaries",
            "hub no inline payload": "contain references only",
            "hub carrier": HUB_CARRIER,
            "newline handling": "LF/CRLF",
            "dry-run parity": "Dry runs calculate the same selections",
            "manifest redaction": "contains no payload text",
            "central byte index": "exact insertion ranges",
            "no visible metadata": "No visible hash, wrapper marker, position label",
            "indexed removal": "repel remove",
            "modified removal refusal": "Cleanup rejects files edited after scattering",
            "multi-position flag": "--file-positions head,mid,tail",
            "instruction-file flag": "--instruction-files",
            "instruction carriers": "`CLAUDE.md`, `AGENTS.md`, and `MEMORY.md`",
            "instruction prevalidation": "validated before any source-file write",
            "placement limitation": "Placement is text-based rather than parser-aware",
            "default all eligible": "Omitting `--count` selects every eligible file by default",
            "mainstream languages": "Mainstream language coverage includes Python, Ruby, JavaScript/TypeScript",
            "test sources": "Test directories receive no special exclusion",
            "shebang scripts": "recognized shebang scripts",
            "commentless exclusion": "commentless structured files such as plain JSON",
            "paired delimiter safety": "Paired comment delimiters are validated",
            "separate instruction layouts": "`with_instruction_files`",
            "separate non-instruction layout": "`without_instruction_files`",
            "coverage threshold": "100% line-and-branch coverage contract",
        }

        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                self.assertIn(f"`{strategy}`", documentation)
        for requirement, expected_text in required_concepts.items():
            with self.subTest(requirement=requirement):
                self.assertIn(expected_text, documentation)


if __name__ == "__main__":
    unittest.main()
