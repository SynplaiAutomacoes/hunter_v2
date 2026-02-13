from __future__ import annotations


def render_pdf_from_url(url: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright nao instalado. Execute: uv add playwright && uv run playwright install chromium") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1280, "height": 1810})
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.emulate_media(media="screen")
        pdf_bytes = page.pdf(format="A4", print_background=True)
        browser.close()
        return pdf_bytes
