"""Tests for the rules. Standard library only: `python -m unittest discover -s tests`."""

import tempfile
import unittest
from pathlib import Path

from profilelint.rules import lint, summarize


def rules_of(findings):
    return {f.rule for f in findings}


class AltTextTests(unittest.TestCase):
    def test_markdown_image_without_alt_is_an_error(self):
        findings = lint("# P\n\n![](./a.png)\n")
        self.assertIn("alt-text", rules_of(findings))

    def test_html_image_without_alt_is_an_error(self):
        findings = lint('# P\n\n<img src="./a.png" width="100%">\n')
        self.assertIn("alt-text", rules_of(findings))

    def test_descriptive_alt_passes(self):
        findings = lint('# P\n\n<img src="./a.png" alt="A meaningful description of the image">\n')
        self.assertNotIn("alt-text", rules_of(findings))


class ImageTests(unittest.TestCase):
    def test_remote_image_is_a_warning(self):
        findings = lint("# P\n\n![chart](https://example.com/card.svg)\n")
        self.assertIn("remote-image", rules_of(findings))
        self.assertTrue(summarize(findings)["ok"])


class ClaimTests(unittest.TestCase):
    def test_hype_is_rejected(self):
        for phrase in ("world-class engineering", "10x faster", "rockstar developer"):
            with self.subTest(phrase=phrase):
                findings = lint(f"# P\n\nI am a {phrase}.\n")
                self.assertIn("claim", rules_of(findings))
                self.assertFalse(summarize(findings)["ok"])


class LinkTests(unittest.TestCase):
    def test_missing_local_path_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = lint("# P\n\n[doc](./missing.md)\n", Path(tmp))
            self.assertIn("missing-path", rules_of(findings))

    def test_existing_local_path_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "present.md").write_text("ok", encoding="utf-8")
            findings = lint("# P\n\n[doc](./present.md)\n", Path(tmp))
            self.assertNotIn("missing-path", rules_of(findings))

    def test_anchor_only_link_is_ignored(self):
        findings = lint("# P\n\n[top](#p)\n", Path("."))
        self.assertNotIn("missing-path", rules_of(findings))

    def test_dead_link_uses_injected_status(self):
        findings = lint("# P\n\n[repo](https://example.com/gone)\n", None, url_status=lambda url: 404)
        self.assertIn("dead-link", rules_of(findings))

    def test_live_link_passes_with_injected_status(self):
        findings = lint("# P\n\n[repo](https://example.com/ok)\n", None, url_status=lambda url: 200)
        self.assertNotIn("dead-link", rules_of(findings))

    def test_head_refusal_is_not_a_dead_link(self):
        for status in (403, 405, 429, 503):
            with self.subTest(status=status):
                findings = lint("# P\n\n[x](https://example.com/x)\n", None, url_status=lambda url: status)
                self.assertIn("unverified-link", rules_of(findings))
                self.assertNotIn("dead-link", rules_of(findings))
                self.assertTrue(summarize(findings)["ok"])

    def test_javascript_scheme_is_rejected(self):
        findings = lint("# P\n\n[x](javascript:alert(1))\n")
        self.assertIn("scheme", rules_of(findings))


class StructureTests(unittest.TestCase):
    def test_empty_readme(self):
        self.assertEqual(rules_of(lint("   \n")), {"empty"})

    def test_missing_h1_is_a_warning_only(self):
        findings = lint("Just a sentence.\n")
        self.assertIn("heading", rules_of(findings))
        self.assertTrue(summarize(findings)["ok"])

    def test_size_budget(self):
        findings = lint("# P\n" + ("x" * 200), None, max_bytes=100)
        self.assertIn("size", rules_of(findings))

    def test_widget_dependency_is_flagged(self):
        findings = lint("# P\n\n![s](https://img.shields.io/badge/a-b-blue)\n")
        self.assertIn("widget", rules_of(findings))


if __name__ == "__main__":
    unittest.main()
