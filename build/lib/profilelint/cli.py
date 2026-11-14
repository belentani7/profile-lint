"""Command line entry point: `profile-lint README.md`."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .rules import MAX_BYTES, lint, summarize

UA = {"User-Agent": "profile-lint/0.1 (+https://github.com)"}


def http_status(url: str, timeout: float = 8.0):
    request = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profile-lint",
        description="Check a GitHub profile README for dead links, missing alt text and unverifiable claims.",
    )
    parser.add_argument("readme", nargs="?", default="README.md", help="path to the README (default: README.md)")
    parser.add_argument("--root", default=None, help="directory that relative links resolve against (default: README's folder)")
    parser.add_argument("--links", action="store_true", help="also request every external link (network)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES, help=f"size budget in bytes (default: {MAX_BYTES})")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.readme)
    if not path.is_file():
        print(f"profile-lint: not a file: {path}", file=sys.stderr)
        return 2

    root = Path(args.root) if args.root else path.parent
    text = path.read_text(encoding="utf-8")
    findings = lint(
        text,
        root,
        url_status=http_status if args.links else None,
        max_bytes=args.max_bytes,
    )
    summary = summarize(findings)

    if args.json:
        payload = {
            "file": str(path),
            "bytes": len(text.encode("utf-8")),
            "summary": summary,
            "findings": [f.as_dict() for f in findings],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for finding in findings:
            label = "error" if finding.severity == "error" else "warn "
            print(f"{path}:{finding.line}: {label} [{finding.rule}] {finding.message}")
        state = "ok" if summary["ok"] else "failed"
        print(
            f"\n{state}: {summary['errors']} error(s), {summary['warnings']} warning(s), "
            f"{len(text.encode('utf-8'))} bytes"
        )

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
