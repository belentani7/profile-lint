"""Reglas deterministas para comprobar README de perfiles sin dependencias externas."""

from __future__ import annotations

import re
import string
from bisect import bisect_right
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

MAX_BYTES = 12_000
DEFAULT_LINK_WORKERS = 8

HYPE = (
    "world-class",
    "cutting-edge",
    "10x faster",
    "ninja",
    "rockstar",
    "guru",
    "replaced a 10-person team",
)

# Una respuesta de estos códigos no demuestra que el recurso haya desaparecido:
# puede ser un reto anti-bots, un recurso privado o un rechazo al método HEAD.
UNVERIFIABLE = (401, 403, 405, 408, 429, 451, 999)

WIDGET_HOSTS = (
    "shields.io",
    "github-readme-stats",
    "visitor-badge",
    "readme-typing-svg",
    "streak-stats",
)

WEB_SCHEMES = {"http", "https"}
SAFE_NON_WEB_SCHEMES = {"mailto", "tel"}
UNSAFE_SCHEMES = {"data", "file", "javascript", "vbscript"}
HYPE_PATTERNS = tuple(
    (phrase, re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.I)) for phrase in HYPE
)

H1 = re.compile(r"^ {0,3}#[ \t]+\S", re.M)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
AUTOLINK = re.compile(r"(?<!\\)<(?P<url>(?:https?://|mailto:|tel:)[^<>\s]+)>", re.I)
BARE_URL = re.compile(r"(?i)(?<!\w)(?<![=<])https?://[^\s<>]+")
REFERENCE_DEFINITION = re.compile(
    r"(?m)^[ \t]{0,3}\[(?P<label>[^\]\n]+)\]:[ \t]*"
    r"(?:<(?P<angle>[^>\n]*)>|(?P<bare>(?:\\.|[^\s])+))"
)


@dataclass(frozen=True)
class Finding:
    """Un hallazgo individual, con ubicación y severidad estable para JSON."""

    rule: str
    severity: str
    line: int
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
        }


@dataclass(frozen=True)
class _LinkTarget:
    value: str
    offset: int
    image: bool = False


def _mask_span(chars: list[str], start: int, end: int) -> None:
    """Reemplaza un tramo por espacios y conserva los saltos de línea y offsets."""
    for index in range(start, end):
        if chars[index] not in "\r\n":
            chars[index] = " "


def _is_escaped(chars: list[str], index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and chars[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _find_code_span_end(chars: list[str], start: int, delimiter_size: int) -> int | None:
    index = start
    while index < len(chars):
        if chars[index] != "`" or _is_escaped(chars, index):
            index += 1
            continue
        end = index + 1
        while end < len(chars) and chars[end] == "`":
            end += 1
        if end - index == delimiter_size:
            return index
        index = end
    return None


def _mask_code(text: str) -> str:
    """Oculta bloques y spans de código sin alterar offsets ni numeración de líneas."""
    chars = list(text)
    fence_character: str | None = None
    fence_size = 0
    offset = 0

    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_character is not None:
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_size},}}[ \t]*", content
            )
            _mask_span(chars, offset, offset + len(line))
            if closing:
                fence_character = None
                fence_size = 0
        else:
            opening = re.match(r" {0,3}(`{3,}|~{3,})", content)
            if opening:
                marker = opening.group(1)
                if marker[0] != "`" or "`" not in content[opening.end() :]:
                    fence_character = marker[0]
                    fence_size = len(marker)
                    _mask_span(chars, offset, offset + len(line))
        offset += len(line)

    index = 0
    while index < len(chars):
        if chars[index] != "`" or _is_escaped(chars, index):
            index += 1
            continue
        delimiter_end = index + 1
        while delimiter_end < len(chars) and chars[delimiter_end] == "`":
            delimiter_end += 1
        delimiter_size = delimiter_end - index
        closing = _find_code_span_end(chars, delimiter_end, delimiter_size)
        if closing is None:
            index = delimiter_end
            continue
        closing_end = closing + delimiter_size
        _mask_span(chars, index, closing_end)
        index = closing_end

    return "".join(chars)


def _mask_html_comments(text: str) -> str:
    chars = list(text)
    for match in HTML_COMMENT.finditer(text):
        _mask_span(chars, match.start(), match.end())
    return "".join(chars)


def _line_starts(text: str) -> list[int]:
    return [0] + [index + 1 for index, char in enumerate(text) if char == "\n"]


def _line_number(line_starts: list[int], offset: int) -> int:
    return bisect_right(line_starts, offset)


def _find_closing_bracket(text: str, opening: int) -> int | None:
    depth = 0
    index = opening
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            index += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _skip_title(text: str, index: int) -> int | None:
    opener = text[index]
    if opener in "\"'":
        index += 1
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                index += 2
            elif text[index] == opener:
                return index + 1
            else:
                index += 1
        return None

    depth = 1
    index += 1
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
        elif text[index] == "(":
            depth += 1
            index += 1
        elif text[index] == ")":
            depth -= 1
            index += 1
            if depth == 0:
                return index
        else:
            index += 1
    return None


def _unescape_target(target: str) -> str:
    result: list[str] = []
    index = 0
    escapable = string.punctuation + " "
    while index < len(target):
        if target[index] == "\\" and index + 1 < len(target) and target[index + 1] in escapable:
            result.append(target[index + 1])
            index += 2
        else:
            result.append(target[index])
            index += 1
    return "".join(result)


def _parse_inline_destination(text: str, opening: int) -> tuple[str, int] | None:
    """Devuelve (destino, fin) para un destino Markdown entre paréntesis."""
    index = opening + 1
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return None
    if text[index] == ")":
        return "", index + 1

    if text[index] == "<":
        start = index + 1
        index = start
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                index += 2
            elif text[index] == ">":
                break
            elif text[index] in "\r\n":
                return None
            else:
                index += 1
        if index >= len(text):
            return None
        target = text[start:index]
        index += 1
    else:
        start = index
        depth = 0
        while index < len(text):
            char = text[index]
            if char == "\\" and index + 1 < len(text):
                index += 2
                continue
            if char.isspace():
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if depth:
            return None
        target = text[start:index]

    target = _unescape_target(target)
    while index < len(text) and text[index].isspace():
        index += 1
    if index < len(text) and text[index] == ")":
        return target, index + 1
    if index < len(text) and text[index] in "\"'(":
        title_end = _skip_title(text, index)
        if title_end is None:
            return None
        index = title_end
        while index < len(text) and text[index].isspace():
            index += 1
        if index < len(text) and text[index] == ")":
            return target, index + 1
    return None


def _reference_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _range_contains(offset: int, ranges: list[tuple[int, int]], starts: list[int]) -> bool:
    position = bisect_right(starts, offset) - 1
    return position >= 0 and offset < ranges[position][1]


def _trim_url_punctuation(url: str) -> str:
    while url and url[-1] in ".,;:!?\\\"'":
        url = url[:-1]
    for closing, opening in ((")", "("), ("]", "["), ("}", "{")):
        while url.endswith(closing) and url.count(closing) > url.count(opening):
            url = url[:-1]
    return url


def _extract_markdown(
    searchable: str,
) -> tuple[list[_LinkTarget], list[int]]:
    targets: list[_LinkTarget] = []
    missing_alt: list[int] = []
    definitions: dict[str, str] = {}
    definition_positions: set[int] = set()
    covered_ranges: list[tuple[int, int]] = []
    searchable_chars = list(searchable)

    for match in REFERENCE_DEFINITION.finditer(searchable):
        value = match.group("angle")
        if value is None:
            value = match.group("bare")
        if value is not None:
            definitions.setdefault(_reference_key(match.group("label")), _unescape_target(value))
            definition_positions.add(match.start("label") - 1)
            line_end = searchable.find("\\n", match.end())
            covered_ranges.append((match.start(), len(searchable) if line_end < 0 else line_end))

    index = 0
    while index < len(searchable):
        if index in definition_positions:
            line_end = searchable.find("\n", index)
            index = len(searchable) if line_end < 0 else line_end + 1
            continue

        image = (
            searchable[index] == "!"
            and index + 1 < len(searchable)
            and searchable[index + 1] == "["
        )
        if image:
            opening = index + 1
        elif searchable[index] == "[":
            opening = index
        else:
            index += 1
            continue

        if _is_escaped(searchable_chars, opening):
            index += 1
            continue
        closing = _find_closing_bracket(searchable, opening)
        if closing is None:
            index = opening + 1
            continue

        label = searchable[opening + 1 : closing]
        if image and not label.strip():
            missing_alt.append(index)

        after_label = closing + 1
        if after_label < len(searchable) and searchable[after_label] == "(":
            parsed = _parse_inline_destination(searchable, after_label)
            if parsed is not None:
                value, end = parsed
                if value:
                    targets.append(_LinkTarget(value, index, image))
                    covered_ranges.append((index, end))
                index = end
                continue

        if after_label < len(searchable) and searchable[after_label] == "[":
            reference_end = _find_closing_bracket(searchable, after_label)
            if reference_end is not None:
                reference = searchable[after_label + 1 : reference_end] or label
                value = definitions.get(_reference_key(reference))
                if value:
                    targets.append(_LinkTarget(value, index, image))
                index = reference_end + 1
                continue

        value = definitions.get(_reference_key(label))
        if value:
            targets.append(_LinkTarget(value, index, image))
        index = closing + 1

    covered_ranges.sort()
    covered_starts = [start for start, _ in covered_ranges]
    angle_ranges: list[tuple[int, int]] = []
    for match in AUTOLINK.finditer(searchable):
        if _range_contains(match.start(), covered_ranges, covered_starts):
            continue
        targets.append(_LinkTarget(match.group("url"), match.start()))
        angle_ranges.append((match.start(), match.end()))

    bare_ranges = sorted(covered_ranges + angle_ranges)
    bare_starts = [start for start, _ in bare_ranges]
    for match in BARE_URL.finditer(searchable):
        if _range_contains(match.start(), bare_ranges, bare_starts):
            continue
        if match.start() and searchable[match.start() - 1] in {'"', "'"}:
            continue
        value = _trim_url_punctuation(match.group(0))
        if value:
            targets.append(_LinkTarget(value, match.start()))

    return targets, missing_alt


class _HTMLLinkParser(HTMLParser):
    """Extrae enlaces e imágenes HTML y conserva sus offsets originales."""

    def __init__(self, line_starts: list[int]) -> None:
        super().__init__(convert_charrefs=True)
        self.line_starts = line_starts
        self.targets: list[_LinkTarget] = []
        self.missing_alt: list[int] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values: dict[str, str | None] = {}
        for name, value in attrs:
            if name not in values:
                values[name] = value

        offset = self._offset()
        if tag == "img":
            alt = values.get("alt")
            if "alt" not in values or alt is None or (alt and not alt.strip()):
                self.missing_alt.append(offset)
            src = values.get("src")
            if src and src.strip():
                self.targets.append(_LinkTarget(src.strip(), offset, image=True))
        elif tag in {"a", "area"}:
            href = values.get("href")
            if href and href.strip():
                self.targets.append(_LinkTarget(href.strip(), offset))


def _valid_web_host(parts: SplitResult) -> bool:
    try:
        _ = parts.port
        return bool(parts.hostname)
    except ValueError:
        return False


def _web_url(target: str, parts: SplitResult) -> str | None:
    """Normaliza URL web y descarta fragmentos que no se envían al servidor."""
    scheme = parts.scheme.lower()
    if scheme in WEB_SCHEMES and parts.netloc and _valid_web_host(parts):
        return parts._replace(fragment="").geturl()
    if not scheme and target.startswith("//") and parts.netloc and _valid_web_host(parts):
        return parts._replace(scheme="https", fragment="").geturl()
    return None


def _is_widget_host(host: str) -> bool:
    labels = host.rstrip(".").split(".")
    return (
        host == "shields.io"
        or host.endswith(".shields.io")
        or any(marker in labels for marker in WIDGET_HOSTS if "." not in marker)
    )


def _get_statuses(
    urls: list[str],
    url_status: Callable[[str], int | None],
    workers: int,
) -> dict[str, int | None]:
    if not urls:
        return {}
    if workers == 1 or len(urls) == 1:
        return {url: url_status(url) for url in urls}
    with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as executor:
        statuses = list(executor.map(url_status, urls))
    return dict(zip(urls, statuses))


def lint(
    text: str,
    root: Path | None = None,
    *,
    url_status: Callable[[str], int | None] | None = None,
    max_bytes: int = MAX_BYTES,
    link_workers: int = 1,
) -> list[Finding]:
    """Devuelve hallazgos ordenados por línea y regla.

    ``url_status`` solo se invoca cuando se proporciona explícitamente. Si
    ``link_workers`` es mayor que uno, el callback puede ejecutarse en paralelo;
    su valor predeterminado conserva el comportamiento serial de la API.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes no puede ser negativo")
    if link_workers < 1:
        raise ValueError("link_workers debe ser al menos 1")

    findings: list[Finding] = []
    if not text.strip():
        return [Finding("empty", "error", 1, "El README está vacío")]

    byte_size = len(text.encode("utf-8"))
    searchable = _mask_html_comments(_mask_code(text))
    line_starts = _line_starts(text)
    if not H1.search(searchable):
        findings.append(
            Finding("heading", "warning", 1, "falta un encabezado de nivel 1 (# título)")
        )
    if byte_size > max_bytes:
        findings.append(
            Finding(
                "size", "warning", 1, f"{byte_size} bytes superan el límite de {max_bytes} bytes"
            )
        )
    for phrase, pattern in HYPE_PATTERNS:
        for match in pattern.finditer(searchable):
            line = _line_number(line_starts, match.start())
            findings.append(
                Finding("claim", "error", line, f"afirmación promocional sin verificar: {phrase!r}")
            )

    markdown_targets, markdown_missing_alt = _extract_markdown(searchable)
    html_parser = _HTMLLinkParser(line_starts)
    html_parser.feed(searchable)
    html_parser.close()
    targets = markdown_targets + html_parser.targets

    for offset in markdown_missing_alt:
        findings.append(
            Finding(
                "alt-text",
                "error",
                _line_number(line_starts, offset),
                "imagen Markdown sin texto alternativo",
            )
        )
    for offset in html_parser.missing_alt:
        findings.append(
            Finding(
                "alt-text",
                "error",
                _line_number(line_starts, offset),
                "imagen HTML sin un texto alternativo válido",
            )
        )

    remote_targets: list[tuple[_LinkTarget, str]] = []
    checked_urls: set[str] = set()
    base = Path(root) if root is not None else None

    for target in targets:
        raw_target = target.value.strip()
        if not raw_target:
            continue
        try:
            parts = urlsplit(raw_target)
        except ValueError:
            findings.append(
                Finding(
                    "scheme",
                    "error",
                    _line_number(line_starts, target.offset),
                    f"URL mal formada: {raw_target[:60]}",
                )
            )
            continue

        scheme = parts.scheme.lower()
        line = _line_number(line_starts, target.offset)
        if scheme in UNSAFE_SCHEMES:
            findings.append(
                Finding("scheme", "error", line, f"esquema de enlace no seguro: {scheme}:")
            )
            continue
        if scheme and scheme not in WEB_SCHEMES | SAFE_NON_WEB_SCHEMES:
            findings.append(
                Finding("scheme", "error", line, f"esquema de enlace no admitido: {scheme}:")
            )
            continue

        web_url = _web_url(raw_target, parts)
        if not scheme and raw_target.startswith("//") and web_url is None:
            findings.append(
                Finding(
                    "scheme",
                    "error",
                    line,
                    "la URL relativa a protocolo debe incluir un host válido",
                )
            )
            continue
        if scheme in WEB_SCHEMES and web_url is None:
            findings.append(
                Finding("scheme", "error", line, "la URL HTTP(S) debe incluir un host válido")
            )
            continue
        if web_url is not None and any(char.isspace() for char in raw_target):
            findings.append(
                Finding("scheme", "error", line, "la URL web contiene espacios sin codificar")
            )
            continue

        if web_url is not None:
            remote_targets.append((target, web_url))
            if target.image:
                findings.append(
                    Finding(
                        "remote-image",
                        "warning",
                        line,
                        f"la imagen se carga desde la red: {web_url[:80]}",
                    )
                )
            host = parts.hostname.lower() if parts.hostname else ""
            if _is_widget_host(host):
                findings.append(
                    Finding("widget", "warning", line, f"depende de un widget externo: {host}")
                )
            checked_urls.add(web_url)
            continue

        if scheme in SAFE_NON_WEB_SCHEMES or scheme:
            continue
        if base is not None and parts.path:
            relative = unquote(parts.path)
            local_path = base / relative.lstrip("/")
            if not local_path.exists():
                findings.append(
                    Finding(
                        "missing-path", "error", line, f"no existe la ruta local: {relative[:90]}"
                    )
                )

    statuses = (
        _get_statuses(sorted(checked_urls), url_status, link_workers)
        if url_status is not None
        else {}
    )
    for target, web_url in remote_targets:
        status = statuses.get(web_url)
        if status is None or status < 400:
            continue
        line = _line_number(line_starts, target.offset)
        if status in UNVERIFIABLE or status >= 500:
            findings.append(
                Finding(
                    "unverified-link",
                    "warning",
                    line,
                    (
                        f"HTTP {status}: el rechazo a HEAD no prueba que el enlace esté roto "
                        f"({web_url[:80]})"
                    ),
                )
            )
        else:
            findings.append(Finding("dead-link", "error", line, f"HTTP {status}: {web_url[:90]}"))

    return sorted(findings, key=lambda finding: (finding.line, finding.rule, finding.message))


def summarize(findings: Iterable[Finding]) -> dict[str, object]:
    """Resume errores y avisos; solo los errores hacen fallar el proceso."""
    findings = list(findings)
    errors = sum(finding.severity == "error" for finding in findings)
    warnings = sum(finding.severity == "warning" for finding in findings)
    return {"errors": errors, "warnings": warnings, "ok": errors == 0}
