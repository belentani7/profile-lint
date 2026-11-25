"""Pruebas unitarias de reglas sin solicitudes de red."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from profilelint.rules import Finding, lint, summarize


def rules_of(findings: list[Finding]) -> set[str]:
    return {finding.rule for finding in findings}


class StructureTests(unittest.TestCase):
    def test_empty_readme(self) -> None:
        findings = lint("   \n")
        self.assertEqual(rules_of(findings), {"empty"})
        self.assertEqual(findings[0].line, 1)

    def test_missing_h1_is_a_warning_only(self) -> None:
        findings = lint("Solo una frase.\n")
        self.assertIn("heading", rules_of(findings))
        self.assertTrue(summarize(findings)["ok"])

    def test_h1_allows_commonmark_indentation(self) -> None:
        self.assertNotIn("heading", rules_of(lint("   # Perfil\n")))

    def test_heading_inside_code_is_not_a_real_heading(self) -> None:
        findings = lint("```markdown\n# Código\n```\n")
        self.assertIn("heading", rules_of(findings))

    def test_size_budget_counts_utf8_bytes(self) -> None:
        findings = lint("# Perfil\nñ", max_bytes=10)
        self.assertIn("size", rules_of(findings))
        self.assertIn("11 bytes", next(f.message for f in findings if f.rule == "size"))

    def test_zero_byte_budget_is_allowed(self) -> None:
        self.assertIn("size", rules_of(lint("# P", max_bytes=0)))

    def test_negative_size_budget_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_bytes"):
            lint("# P", max_bytes=-1)

    def test_error_free_and_warning_only_summaries(self) -> None:
        summary = summarize([Finding("heading", "warning", 1, "aviso")])
        self.assertEqual(summary, {"errors": 0, "warnings": 1, "ok": True})


class AltTextTests(unittest.TestCase):
    def test_markdown_image_without_alt_is_an_error(self) -> None:
        findings = lint("# Perfil\n\n![](./a.png)\n")
        self.assertIn("alt-text", rules_of(findings))
        self.assertEqual(next(f.line for f in findings if f.rule == "alt-text"), 3)

    def test_html_image_without_alt_is_an_error(self) -> None:
        findings = lint('# Perfil\n\n<img src="./a.png" width="100%">\n')
        self.assertIn("alt-text", rules_of(findings))

    def test_html_image_with_unquoted_alt_is_parsed(self) -> None:
        findings = lint("# Perfil\n\n<img src=./a.png alt=Retrato>\n")
        self.assertNotIn("alt-text", rules_of(findings))

    def test_empty_html_alt_is_valid_for_a_decorative_image(self) -> None:
        findings = lint('# Perfil\n\n<img src="./a.png" alt="">\n')
        self.assertNotIn("alt-text", rules_of(findings))

    def test_html_boolean_alt_is_not_a_text_alternative(self) -> None:
        findings = lint("# Perfil\\n\\n<img src=./a.png alt>\\n")
        self.assertIn("alt-text", rules_of(findings))

    def test_whitespace_only_html_alt_is_not_a_text_alternative(self) -> None:
        findings = lint('<img src="./a.png" alt="   ">')
        self.assertIn("alt-text", rules_of(findings))

    def test_image_in_a_code_block_is_ignored(self) -> None:
        findings = lint("# Perfil\n\n```md\n![](https://example.test/card.svg)\n```\n")
        self.assertNotIn("alt-text", rules_of(findings))
        self.assertNotIn("remote-image", rules_of(findings))


class ImageAndWidgetTests(unittest.TestCase):
    def test_remote_markdown_image_is_a_warning(self) -> None:
        findings = lint("# Perfil\n\n![gráfico](https://example.test/card.svg)\n")
        self.assertIn("remote-image", rules_of(findings))
        self.assertTrue(summarize(findings)["ok"])

    def test_unquoted_html_image_url_is_detected(self) -> None:
        findings = lint("# Perfil\n\n<img src=https://img.example.test/card.svg alt=Gráfico>\n")
        self.assertIn("remote-image", rules_of(findings))

    def test_widget_host_is_detected_from_link_target(self) -> None:
        findings = lint("# Perfil\n\n![stats](https://img.shields.io/badge/build-passing-green)\n")
        self.assertIn("widget", rules_of(findings))

    def test_mentioning_a_widget_host_in_prose_is_not_a_dependency(self) -> None:
        findings = lint("# Perfil\n\nEl servicio shields.io no se usa en esta página.\n")
        self.assertNotIn("widget", rules_of(findings))

    def test_widget_marker_is_not_matched_inside_an_unrelated_host(self) -> None:
        findings = lint("# Perfil\n\n![x](https://notshields.io.example.test/badge.svg)\n")
        self.assertNotIn("widget", rules_of(findings))

    def test_widget_inside_code_is_ignored(self) -> None:
        findings = lint("# Perfil\n\n`![stats](https://img.shields.io/badge/x-y)`\n")
        self.assertNotIn("widget", rules_of(findings))
        self.assertNotIn("remote-image", rules_of(findings))


class ClaimTests(unittest.TestCase):
    def test_hype_phrases_are_rejected_case_insensitively(self) -> None:
        for phrase in ("world-class engineering", "10x faster", "ROCKSTAR developer"):
            with self.subTest(phrase=phrase):
                findings = lint(f"# Perfil\n\nSoy {phrase}.\n")
                self.assertIn("claim", rules_of(findings))
                self.assertFalse(summarize(findings)["ok"])

    def test_claim_phrases_respect_word_boundaries(self) -> None:
        findings = lint("# Perfil\\n\\nUn superninja y unworld-class.\\n")
        self.assertNotIn("claim", rules_of(findings))

    def test_code_and_comments_do_not_create_claim_findings(self) -> None:
        findings = lint(
            "# Perfil\\n\\n`rockstar`\\n\\n"
            "<!-- cutting-edge -->\\n\\n"
            "```text\\nworld-class\\n```\\n"
        )
        self.assertNotIn("claim", rules_of(findings))

    def test_claim_line_number_is_reported(self) -> None:
        findings = lint("# Perfil\n\nUna frase.\nSoy un ninja.\n")
        claim = next(finding for finding in findings if finding.rule == "claim")
        self.assertEqual(claim.line, 4)


class LocalLinkTests(unittest.TestCase):
    def test_missing_local_path_is_an_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            findings = lint("# Perfil\n\n[documento](./missing.md)\n", Path(temp_dir))
            self.assertIn("missing-path", rules_of(findings))

    def test_existing_local_path_passes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "present.md").write_text("ok", encoding="utf-8")
            findings = lint("# Perfil\n\n[documento](./present.md)\n", Path(temp_dir))
            self.assertNotIn("missing-path", rules_of(findings))

    def test_encoded_path_with_query_and_fragment_resolves(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "captura final.png").write_text("x", encoding="utf-8")
            findings = lint(
                "# Perfil\n\n![captura](./captura%20final.png?raw=1#vista)\n",
                Path(temp_dir),
            )
            self.assertNotIn("missing-path", rules_of(findings))

    def test_angle_destination_can_contain_spaces_and_parentheses(self) -> None:
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir, "carpeta con espacios")
            folder.mkdir()
            (folder / "imagen (final).png").write_text("x", encoding="utf-8")
            findings = lint(
                "# Perfil\n\n![captura](<./carpeta con espacios/imagen (final).png>)\n",
                Path(temp_dir),
            )
            self.assertNotIn("missing-path", rules_of(findings))

    def test_balanced_parentheses_in_bare_destination_are_supported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "a_(b).md").write_text("x", encoding="utf-8")
            findings = lint("# Perfil\n\n[documento](./a_(b).md)\n", Path(temp_dir))
            self.assertNotIn("missing-path", rules_of(findings))

    def test_markdown_link_title_does_not_become_part_of_the_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "present.md").write_text("x", encoding="utf-8")
            findings = lint(
                '# Perfil\n\n[documento](./present.md "título")\n',
                Path(temp_dir),
            )
            self.assertNotIn("missing-path", rules_of(findings))

    def test_html_anchor_local_path_is_checked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            findings = lint('# Perfil\n\n<a href="./missing.md">doc</a>\n', Path(temp_dir))
            self.assertIn("missing-path", rules_of(findings))

    def test_reference_links_and_reference_images_are_checked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "guide.md").write_text("x", encoding="utf-8")
            findings = lint(
                "# Perfil\n\n[guía][doc]\n![gráfico][chart]\n\n"
                "[doc]: ./guide.md\n"
                "[chart]: https://charts.example.test/profile.svg\n",
                Path(temp_dir),
            )
            self.assertNotIn("missing-path", rules_of(findings))
            self.assertIn("remote-image", rules_of(findings))

    def test_bare_auto_link_is_checked_without_trailing_punctuation(self) -> None:
        checked: list[str] = []

        def status(url: str) -> int:
            checked.append(url)
            return 404

        findings = lint("# Perfil\n\nhttps://example.test/repo).\n", url_status=status)
        self.assertEqual(checked, ["https://example.test/repo"])
        self.assertIn("dead-link", rules_of(findings))

    def test_angle_bracket_auto_link_is_checked(self) -> None:
        findings = lint("# Perfil\n\n<https://example.test/repo>\n", url_status=lambda _: 404)
        self.assertIn("dead-link", rules_of(findings))

    def test_anchor_only_link_is_ignored(self) -> None:
        findings = lint("# Perfil\n\n[top](#perfil)\n", Path("."))
        self.assertNotIn("missing-path", rules_of(findings))

    def test_local_path_finding_has_the_link_line(self) -> None:
        with TemporaryDirectory() as temp_dir:
            findings = lint("# Perfil\n\nUna frase.\n[doc](./missing)\n", Path(temp_dir))
            missing = next(finding for finding in findings if finding.rule == "missing-path")
            self.assertEqual(missing.line, 4)


class ExternalLinkTests(unittest.TestCase):
    def test_dead_link_uses_injected_status(self) -> None:
        findings = lint("# Perfil\n\n[repo](https://example.test/gone)\n", url_status=lambda _: 404)
        self.assertIn("dead-link", rules_of(findings))

    def test_live_link_passes_with_injected_status(self) -> None:
        findings = lint("# Perfil\n\n[repo](https://example.test/ok)\n", url_status=lambda _: 200)
        self.assertNotIn("dead-link", rules_of(findings))

    def test_head_refusals_and_server_errors_are_not_dead_links(self) -> None:
        for status in (401, 403, 405, 408, 429, 451, 500, 503):
            with self.subTest(status=status):
                findings = lint(
                    "# Perfil\n\n[x](https://example.test/x)\n",
                    url_status=lambda _, response=status: response,
                )
                self.assertIn("unverified-link", rules_of(findings))
                self.assertNotIn("dead-link", rules_of(findings))
                self.assertTrue(summarize(findings)["ok"])

    def test_html_link_is_not_duplicated_by_bare_url_detection(self) -> None:
        checked: list[str] = []

        def status(url: str) -> int:
            checked.append(url)
            return 404

        findings = lint(
            '# Perfil\\n\\n<a href="https://example.test/repo">repositorio</a>\\n',
            url_status=status,
        )
        self.assertEqual(checked, ["https://example.test/repo"])
        self.assertEqual(sum(f.rule == "dead-link" for f in findings), 1)

    def test_duplicate_targets_are_requested_once(self) -> None:
        checked: list[str] = []

        def status(url: str) -> int:
            checked.append(url)
            return 200

        lint(
            "# Perfil\n\n[a](https://example.test/repo)\n[b](https://example.test/repo)\n",
            url_status=status,
        )
        self.assertEqual(checked, ["https://example.test/repo"])

    def test_protocol_relative_links_use_https_for_checks(self) -> None:
        checked: list[str] = []

        def status(url: str) -> int:
            checked.append(url)
            return 404

        findings = lint("# Perfil\n\n[repo](//example.test/project#readme)\n", url_status=status)
        self.assertEqual(checked, ["https://example.test/project"])
        self.assertIn("dead-link", rules_of(findings))

    def test_protocol_relative_url_without_host_is_rejected(self) -> None:
        findings = lint("# Perfil\n\n[enlace](//)\n")
        self.assertIn("scheme", rules_of(findings))
        self.assertNotIn("missing-path", rules_of(findings))

    def test_link_checks_can_run_concurrently(self) -> None:
        barrier = Barrier(2)

        def status(_: str) -> int:
            barrier.wait(timeout=2)
            return 200

        findings = lint(
            "# Perfil\n\n[a](https://one.example.test)\n[b](https://two.example.test)\n",
            url_status=status,
            link_workers=2,
        )
        self.assertNotIn("dead-link", rules_of(findings))

    def test_external_links_are_not_checked_by_default(self) -> None:
        findings = lint("# Perfil\n\n[a](https://example.test)\n")
        self.assertNotIn("dead-link", rules_of(findings))
        self.assertTrue(summarize(findings)["ok"])

    def test_invalid_worker_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "link_workers"):
            lint("# Perfil", link_workers=0)

    def test_malformed_web_url_does_not_crash(self) -> None:
        findings = lint("# Perfil\n\n[enlace](https://[incompleto)\n")
        self.assertIn("scheme", rules_of(findings))

    def test_mailto_and_tel_are_supported_without_network_requests(self) -> None:
        findings = lint("# Perfil\n\n[correo](mailto:a@example.test) [tel](tel:+12345)\n")
        self.assertNotIn("scheme", rules_of(findings))
        self.assertNotIn("dead-link", rules_of(findings))

    def test_unsupported_and_unsafe_schemes_are_rejected(self) -> None:
        for target in (
            "javascript:alert(1)",
            "data:text/plain,hello",
            "vbscript:msgbox(1)",
            "ftp://example.test/file",
        ):
            with self.subTest(target=target):
                findings = lint(f"# Perfil\n\n[enlace]({target})\n")
                self.assertIn("scheme", rules_of(findings))

    def test_code_blocks_comments_and_inline_code_are_not_links(self) -> None:
        findings = lint(
            "# Perfil\n\n"
            "`[inline](javascript:alert(1))`\n\n"
            "<!-- ![](https://hidden.example.test/image.png) -->\n\n"
            "```md\n[code](https://hidden.example.test)\n```\n"
        )
        self.assertNotIn("scheme", rules_of(findings))
        self.assertNotIn("remote-image", rules_of(findings))
        self.assertNotIn("alt-text", rules_of(findings))


if __name__ == "__main__":
    unittest.main()
