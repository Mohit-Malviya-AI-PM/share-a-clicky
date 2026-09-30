"""Serve the page's Google Fonts (Inter, Geist Mono, Caveat) from tests/fixtures/fonts.

Line breaks depend on the exact font, so tests that check wrapping must use the
real fonts even when fonts.googleapis.com is unreachable. Files come from the
@fontsource npm packages (same Google Fonts, OFL licensed).
Usage: route_fonts(page_or_context) before goto.
"""
import os

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "fonts")
FACES = [
    ("Inter", 400, "inter-latin-400-normal.woff2"), ("Inter", 500, "inter-latin-500-normal.woff2"),
    ("Inter", 600, "inter-latin-600-normal.woff2"), ("Inter", 700, "inter-latin-700-normal.woff2"),
    ("Geist Mono", 400, "geist-mono-latin-400-normal.woff2"), ("Geist Mono", 500, "geist-mono-latin-500-normal.woff2"),
    ("Caveat", 700, "caveat-latin-700-normal.woff2"),
]
CSS = "\n".join(
    f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;"
    f"src:url(https://fonts.gstatic.com/local/{file}) format('woff2');}}"
    for family, weight, file in FACES
)


def route_fonts(target):
    target.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=CSS))
    target.route("https://fonts.gstatic.com/local/**", lambda r: r.fulfill(
        status=200, content_type="font/woff2", path=os.path.join(FONT_DIR, r.request.url.rsplit("/", 1)[-1]),
        headers={"Access-Control-Allow-Origin": "*"}))
