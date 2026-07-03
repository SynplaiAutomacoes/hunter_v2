from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

_SCRIPT_DIR = pathlib.Path(__file__).parent
_HELPER_SCRIPT = str(_SCRIPT_DIR / "html_to_pdf.py")


def _render_with_subprocess(html: str | None = None, url: str | None = None) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as html_file:
        if html is not None:
            html_file.write(html)
            html_path = html_file.name
        else:
            html_path = None

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
        pdf_path = pdf_file.name

    try:
        args = [sys.executable, _HELPER_SCRIPT, "--output", pdf_path]
        if url:
            args.extend(["--url", url])
        elif html_path:
            args.extend(["--html-file", html_path])

        result = subprocess.run(args, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                f"PDF subprocess failed (exit={result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )

        pdf_bytes = pathlib.Path(pdf_path).read_bytes()
        if not pdf_bytes:
            raise RuntimeError("PDF subprocess produced empty output")
        return pdf_bytes
    finally:
        if html_path:
            pathlib.Path(html_path).unlink(missing_ok=True)
        pathlib.Path(pdf_path).unlink(missing_ok=True)


def render_pdf_from_html(html: str) -> bytes:
    return _render_with_subprocess(html=html)


def render_pdf_from_url(url: str) -> bytes:
    return _render_with_subprocess(url=url)
