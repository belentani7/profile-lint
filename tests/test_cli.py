"""Pruebas de extremo a extremo de la interfaz de terminal."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from profilelint.cli import USER_AGENT, http_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_cli(
        self, *arguments: str, input_text: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "profilelint.cli", *arguments],
            cwd=PROJECT_ROOT,
            input=input_text,
            capture_output=True,
            check=False,
            text=True,
        )

    def test_happy_path_reads_a_file_and_emits_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "guide.md").write_text("Guía", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text("# Perfil\n\n[guía](./guide.md)\n", encoding="utf-8")

            result = self.run_cli(str(readme), "--root", temp_dir, "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["file"], str(readme))
            self.assertEqual(report["summary"], {"errors": 0, "warnings": 0, "ok": True})
            self.assertEqual(report["findings"], [])

    def test_lint_error_returns_exit_code_one(self) -> None:
        with TemporaryDirectory() as temp_dir:
            readme = Path(temp_dir, "README.md")
            readme.write_text("# Perfil\\n\\n![](./image.png)\\n", encoding="utf-8")

            result = self.run_cli(str(readme), "--json")

            self.assertEqual(result.returncode, 1)
            self.assertIn('"rule": "alt-text"', result.stdout)

    def test_stdin_happy_path_checks_local_paths_when_root_is_given(self) -> None:
        with TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "guide.md").write_text("Guía", encoding="utf-8")
            result = self.run_cli(
                "-",
                "--root",
                temp_dir,
                "--json",
                input_text="# Perfil\n\n[guía](./guide.md)\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["file"], "<stdin>")
            self.assertTrue(report["summary"]["ok"])

    def test_missing_file_returns_exit_code_two_and_explains_the_error(self) -> None:
        result = self.run_cli("/no-existe/README.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no es un archivo", result.stderr)

    def test_negative_byte_limit_is_rejected_by_argparse(self) -> None:
        result = self.run_cli("--max-bytes", "-1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("mayor o igual que cero", result.stderr)

    def test_help_and_version_are_available(self) -> None:
        help_result = self.run_cli("--help")
        version_result = self.run_cli("--version")
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--links", help_result.stdout)
        self.assertEqual(version_result.returncode, 0)
        self.assertIn("profile-lint 0.2.0", version_result.stdout)


class HttpStatusTests(unittest.TestCase):
    def test_sends_head_with_user_agent_and_timeout(self) -> None:
        response = MagicMock()
        response.status = 204
        response.__enter__.return_value = response
        with patch("profilelint.cli.urllib.request.urlopen", return_value=response) as urlopen:
            self.assertEqual(http_status("https://example.test/profile", timeout=1.5), 204)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "HEAD")
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 1.5)

    def test_http_error_status_is_returned(self) -> None:
        error = HTTPError("https://example.test/missing", 404, "Not Found", {}, None)
        with patch("profilelint.cli.urllib.request.urlopen", side_effect=error):
            self.assertEqual(http_status("https://example.test/missing"), 404)

    def test_network_failure_is_unverified(self) -> None:
        with patch(
            "profilelint.cli.urllib.request.urlopen",
            side_effect=URLError("fallo de red"),
        ):
            self.assertIsNone(http_status("https://example.test/"))

    def test_non_web_scheme_is_not_requested(self) -> None:
        with patch("profilelint.cli.urllib.request.urlopen") as urlopen:
            self.assertIsNone(http_status("file:///etc/passwd"))
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
