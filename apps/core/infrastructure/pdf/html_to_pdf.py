import argparse
import pathlib

from playwright.async_api import async_playwright
import asyncio


async def _render(html: str, url: str | None, output_path: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 794, "height": 1123})
        if url:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        else:
            await page.set_content(html, wait_until="domcontentloaded", timeout=60000)
        await page.emulate_media(media="screen")
        await page.pdf(path=output_path, format="A4", print_background=True)
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="URL to render")
    parser.add_argument("--html-file", help="Path to HTML file")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args()

    if args.html_file:
        html = pathlib.Path(args.html_file).read_text(encoding="utf-8")
    else:
        html = ""

    asyncio.run(_render(html=html, url=args.url, output_path=args.output))


if __name__ == "__main__":
    main()
