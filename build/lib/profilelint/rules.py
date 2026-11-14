"""The rules. Each one exists because it caught a real defect in a live profile.

No third-party dependencies: everything is `re`, `pathlib` and `urllib` from the
standard library, so the tool runs anywhere Python runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit

MAX_BYTES = 12_000

HYPE = (
    "world-class",
    "cutting-edge",
    "10x faster",
    "ninja",
    "rockstar",
    "guru",
    "replaced a 10-person team",
)

# Statuses that mean "this host refuses automated clients", not "this page is gone".
# LinkedIn answers 405 to HEAD, Cloudflare-style shields answer 403/429.
UNVERIFIABLE = (403, 405, 429, 999)

WIDGET_HOSTS = (
    "shields.io",
    "github-readme-stats",
    "visitor-badge",
    "readme-typing-svg",
    "streak-stats",
)

MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)")
MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)")
HTML_IMG = re.compile(r"<img\b([^>]*)>", re.I)
ATTR = re.compile(r"\b(src|alt)\s*=\s*[\"']([^\"']*)[\"']", re.I)
H1 = re.compile(r"^#\s+\S", re.M)


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    line: int
    message: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "line": self.line, "message": self.message}


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _is_remote(target: str) -> bool:
    return urlsplit(target).scheme in ("http", "https")


def _is_local(target: str) -> bool:
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc and not target.startswith("#")


def lint(
    text: str,
    root: Optional[Path] = None,
    *,
    url_status: Optional[Callable[[str], Optional[int]]] = None,
    max_bytes: int = MAX_BYTES,
) -> list:
    """Return findings for a profile README, ordered by line."""
    findings = []
    if not text.strip():
        return [Finding("empty", "error", 1, "README is empty")]
    low = text.lower()

    if not H1.search(text):
        findings.append(Finding("heading", "warning", 1, "no top-level '# ' heading"))

    size = len(text.encode("utf-8"))
    if size > max_bytes:
        findings.append(
            Finding("size", "warning", 1, f"{size} bytes exceeds the {max_bytes} byte budget")
        )

    for match in MD_IMAGE.finditer(text):
        alt, src = match.group(1).strip(), match.group(2)
        line = _line_of(text, match.start())
        if not alt:
            findings.append(Finding("alt-text", "error", line, "markdown image has no alt text"))
        if _is_remote(src):
            findings.append(
                Finding("remote-image", "warning", line, f"image is fetched at render time: {src[:80]}")
            )

    for match in HTML_IMG.finditer(text):
        attrs = {k.lower(): v for k, v in ATTR.findall(match.group(1))}
        line = _line_of(text, match.start())
        if not attrs.get("alt", "").strip():
            findings.append(Finding("alt-text", "error", line, "html image has no alt text"))
        if _is_remote(attrs.get("src", "")):
            findings.append(
                Finding("remote-image", "warning", line, f"image is fetched at render time: {attrs['src'][:80]}")
            )

    for host in WIDGET_HOSTS:
        if host in low:
            findings.append(
                Finding("widget", "warning", 1, f"depends on a third-party widget: {host}")
            )

    for term in HYPE:
        if term in low:
            findings.append(
                Finding("claim", "error", 1, f"unverifiable marketing claim: '{term}'")
            )

    targets = [(m.group(2), m.start()) for m in MD_LINK.finditer(text)]
    targets += [(m.group(2), m.start()) for m in MD_IMAGE.finditer(text)]

    for target, index in targets:
        line = _line_of(text, index)
        scheme = urlsplit(target).scheme
        if scheme in ("javascript", "data"):
            findings.append(Finding("scheme", "error", line, f"unsupported link scheme: {target[:60]}"))
        elif _is_remote(target):
            if url_status is not None:
                status = url_status(target)
                if status is not None and status >= 400:
                    if status in UNVERIFIABLE or status >= 500:
                        findings.append(
                            Finding(
                                "unverified-link",
                                "warning",
                                line,
                                f"HTTP {status} to HEAD only, not proof the page is gone: {target[:80]}",
                            )
                        )
                    else:
                        findings.append(
                            Finding("dead-link", "error", line, f"HTTP {status}: {target[:90]}")
                        )
        elif _is_local(target) and root is not None:
            relative = urlsplit(target).path
            if relative and not (Path(root) / relative.lstrip("/")).exists():
                findings.append(
                    Finding("missing-path", "error", line, f"local path does not exist: {relative[:90]}")
                )

    return sorted(findings, key=lambda f: (f.line, f.rule))


def summarize(findings: Iterable[Finding]) -> dict:
    findings = list(findings)
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return {"errors": errors, "warnings": warnings, "ok": errors == 0}
