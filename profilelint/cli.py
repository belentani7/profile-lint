"""Interfaz de línea de comandos para ``profile-lint``."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .rules import DEFAULT_LINK_WORKERS, MAX_BYTES, lint, summarize

HTTP_TIMEOUT_SECONDS = 8.0
USER_AGENT = f"profile-lint/{__version__} (+https://github.com/belentani7/profile-lint)"


def http_status(url: str, timeout: float = HTTP_TIMEOUT_SECONDS) -> int | None:
    """Consulta una URL con HEAD; ``None`` significa que no pudo verificarse."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc or not parts.hostname:
            return None
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
            method="HEAD",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("debe ser un entero") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser un entero mayor o igual que cero")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("debe ser un entero") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("debe ser un entero mayor que cero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profile-lint",
        description=(
            "Comprueba enlaces, accesibilidad básica y afirmaciones difíciles de verificar "
            "en un README de perfil de GitHub."
        ),
    )
    parser.add_argument(
        "readme",
        nargs="?",
        default="README.md",
        help="ruta del README o - para leer desde stdin (por defecto: README.md)",
    )
    parser.add_argument(
        "--root",
        help="directorio base de los enlaces relativos (por defecto: carpeta del README)",
    )
    parser.add_argument(
        "--links",
        action="store_true",
        help="comprueba también los enlaces HTTP(S) con solicitudes HEAD",
    )
    parser.add_argument(
        "--link-workers",
        type=_positive_int,
        default=DEFAULT_LINK_WORKERS,
        help=f"máximo de comprobaciones de red simultáneas (por defecto: {DEFAULT_LINK_WORKERS})",
    )
    parser.add_argument("--json", action="store_true", help="genera un informe JSON")
    parser.add_argument(
        "--max-bytes",
        type=_non_negative_int,
        default=MAX_BYTES,
        help=f"límite de tamaño en bytes (por defecto: {MAX_BYTES})",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _load(args: argparse.Namespace) -> tuple[str | None, Path | None, Path | str]:
    """Lee el archivo indicado o stdin y devuelve su contenido, raíz y etiqueta."""
    if args.readme == "-":
        root = Path(args.root) if args.root else None
        return sys.stdin.read(), root, "<stdin>"

    path = Path(args.readme)
    if not path.is_file():
        return None, None, path
    root = Path(args.root) if args.root else path.parent
    return path.read_text(encoding="utf-8"), root, path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        text, root, label = _load(args)
    except (OSError, UnicodeError) as error:
        print(f"profile-lint: no se pudo leer {args.readme}: {error}", file=sys.stderr)
        return 2

    if text is None:
        print(f"profile-lint: no es un archivo: {label}", file=sys.stderr)
        return 2

    findings = lint(
        text,
        root,
        url_status=http_status if args.links else None,
        max_bytes=args.max_bytes,
        link_workers=args.link_workers,
    )
    summary = summarize(findings)
    byte_size = len(text.encode("utf-8"))

    if args.json:
        payload = {
            "file": str(label),
            "bytes": byte_size,
            "summary": summary,
            "findings": [finding.as_dict() for finding in findings],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for finding in findings:
            severity = "error" if finding.severity == "error" else "aviso"
            print(f"{label}:{finding.line}: {severity} [{finding.rule}] {finding.message}")
        state = "correcto" if summary["ok"] else "falló"
        print(
            f"\n{state}: {summary['errors']} error(es), {summary['warnings']} aviso(s), "
            f"{byte_size} bytes"
        )

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
