"""Browser tests for the share page (headless Chromium via Playwright).

Run: python3 tests/page_check.py [screenshot_dir]
PAGE=v2/ python3 tests/page_check.py   checks the one-page v2 preview at docs/v2/ instead of the live page.
Serves docs/ on a local port, checks acceptance items A1 to A6, saves screenshots.
"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from webfonts import route_fonts  # noqa: E402

def txt(page, selector):
    """Visible text with no-break spaces read as normal spaces (the page glues last words together)."""
    return page.inner_text(selector).replace("\u00a0", " ")


WIDOWS_JS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "widows.js")).read()

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP page tests: install with `pip install playwright && playwright install chromium`")
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
PAGE = os.environ.get("PAGE", "")  # "" = live page, "v2/" = preview
V2 = PAGE == "v2/"


def serve(directory):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(QuietHandler, directory=directory)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


CONTRAST_JS = """
(selector) => {
  function rgba(str) {
    const m = str.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(",").map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  function over(top, bottom) {
    const a = top.a + bottom.a * (1 - top.a);
    const mix = (k) => (top[k] * top.a + bottom[k] * bottom.a * (1 - top.a)) / (a || 1);
    return { r: mix("r"), g: mix("g"), b: mix("b"), a };
  }
  function background(node) {
    const layers = [];
    for (let n = node; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) layers.push(c);
      if (c && c.a === 1) break;
    }
    let result = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = layers.length - 1; i >= 0; i--) result = over(layers[i], result);
    return result;
  }
  function lum(c) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  return [...document.querySelectorAll(selector)].map((node) => {
    const bg = background(node);
    const fg = over(rgba(getComputedStyle(node).color), bg);
    const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
    return (a + 0.05) / (b + 0.05);
  });
}
"""
# Small text that must reach WCAG AA (4.5:1) in both themes.
SMALL_TEXT = "footer span, .tag, .chip, .eyebrow, .step .n, .finding .k, .demo figcaption, .proof figcaption, .muted, .top-right a, .howto .body > span, .kbd, .builder p, .np-label, .tldr span, .faq summary, .mb-links a, .sky .section-head p, .term-bar span, .vp-chip, .vp-jump, footer .credits a, .byline, .steps-line li, .why-list span, .funnel span, .measure .guard, .faq-title"
DETAIL_SMALL_TEXT = "dl.facts dt, .mac-note, .invite-note, .usage-row > span, .by, .back"


def main():
    shots = sys.argv[1] if len(sys.argv) > 1 else None
    if shots:
        os.makedirs(shots, exist_ok=True)
    with open(os.path.join(SITE, "clickys.json")) as data_file:
        data = json.load(data_file)
    failures = []

    def check(label, condition):
        print(("PASS " if condition else "FAIL ") + label)
        if not condition:
            failures.append(label)

    server, base = serve(SITE)
    home = base + PAGE
    broken_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(broken_dir, PAGE), exist_ok=True)
    shutil.copy(os.path.join(SITE, PAGE, "index.html"), os.path.join(broken_dir, PAGE))
    broken_server, broken_base = serve(broken_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            for label, viewport in (("desktop", {"width": 1280, "height": 900}), ("phone", {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport, color_scheme=scheme)
                route_fonts(context)
                context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base.rstrip("/"))
                page = context.new_page()
                errors = []
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: errors.append(str(e)))
                tag = f"{scheme}/{label}"

                page.goto(home)
                page.wait_for_selector(".card")
                check(f"A1 gallery lists all Clickys [{tag}]", page.locator(".card").count() == len(data["clickys"]))
                examples = sum(1 for c in data["clickys"] if c["example"])
                check(f"Example chips match data [{tag}]", page.locator(".chip.example").count() == examples)
                check(f"link preview says unofficial [{tag}]",
                      "Unofficial" in page.get_attribute("meta[property='og:description']", "content"))
                check(f"main is not an aria-live region [{tag}]", page.get_attribute("main", "aria-live") is None)
                no_scroll = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                check(f"A5 no horizontal scroll on gallery [{tag}]", no_scroll)
                ratios = page.evaluate(CONTRAST_JS, SMALL_TEXT)
                check(f"A6 small text contrast >= 4.5 on gallery (min {min(ratios):.2f}) [{tag}]", min(ratios) >= 4.5)
                check(f"first Tab lands on the header, not past it [{tag}]",
                      page.evaluate("document.activeElement === document.body"))
                check(f"demo video has mp4 source and captions [{tag}]",
                      page.locator("#demo video source[type='video/mp4']").count() == 1
                      and page.locator("#demo video track[kind='captions']").count() == 1)
                if label == "desktop":
                    one_line = page.evaluate("""[...document.querySelectorAll('.finding b')].every(b => {
                        const lh = parseFloat(getComputedStyle(b).lineHeight) || 24; return b.getBoundingClientRect().height < lh * 1.5; })""")
                    check(f"finding titles fit on one line [{tag}]", one_line)
                check(f"radio button is off by default [{tag}]", page.get_attribute(".np", "aria-pressed") == "false")
                new_layout = page.locator(".why-list").count() == 1  # the one-page layout (v2 preview, or live after the swap)
                check(f"faq has questions [{tag}]", page.locator("#faq details").count() >= (4 if new_layout else 6))
                check(f"demo uses the custom player, not native controls [{tag}]",
                      page.locator("#demo video[controls]").count() == 0
                      and page.locator("#demo .vp-big").count() == 1
                      and page.locator("#demo .vp-track[role='slider']").count() == 1
                      and page.locator("#demo .vp-chip").count() >= 5)
                check(f"radio skip button hidden until music plays [{tag}]", page.evaluate("document.querySelector('.np-skip').hidden"))
                check(f"radio previous button hidden until music plays [{tag}]", page.evaluate("document.querySelector('.np-prev').hidden"))
                check(f"music credit in the footer [{tag}]", "Kevin MacLeod" in txt(page, "footer") and "creativecommons.org/licenses/by/4.0" in page.inner_html("footer"))
                if new_layout:
                    check(f"v2: stickers only in the hero [{tag}]", page.locator("section .sec-sticker").count() == 0)
                    check(f"v2: 6 nav links [{tag}]", page.locator(".mb-links a").count() == 6)
                    check(f"v2: every old section link still lands [{tag}]", page.evaluate("['demo','shared','how','connector','idea','findings','metrics','faq','builder'].every(id => document.getElementById(id))"))
                    check(f"v2: no repeated summary blocks [{tag}]", page.locator(".tldr, .marquee, .rotator").count() == 0)
                    check(f"v2: under 800 visible words [{tag}]", page.evaluate("document.querySelector('main').innerText.split(/\\s+/).filter(Boolean).length") < 800)
                    if V2:
                        check(f"v2: marked noindex and preview [{tag}]", page.locator("meta[name=robots][content=noindex]").count() == 1 and page.locator(".preview-ribbon").count() == 1)
                    else:
                        check(f"live: no preview label or noindex left [{tag}]", page.locator("meta[name=robots], .preview-ribbon").count() == 0)
                    check(f"v2: email link in about me [{tag}]", page.locator("#builder a[href^='mailto:']").count() == 1)
                    check(f"v2: proof screenshot loads [{tag}]", page.evaluate("new Promise(r => { const i = document.querySelector('.proof img'); i.loading = 'eager'; if (i.complete && i.naturalWidth) r(true); i.onload = () => r(i.naturalWidth > 0); i.onerror = () => r(false); setTimeout(() => r(i.naturalWidth > 0), 8000); })"))
                else:
                    check(f"every section has stickers [{tag}]", page.evaluate("['shared','how','connector','findings','metrics','faq','builder'].every(id => document.querySelector('#' + id + ' .sec-sticker'))"))
                check(f"footer tile wordmark drawn [{tag}]", page.locator("#tiles rect").count() > 100)
                check(f"email chip in about me [{tag}]", page.locator("#builder a[href='mailto:mohit.malviya.cornell@gmail.com']").count() == 1)
                page.evaluate("document.fonts.ready")
                widows = page.evaluate(WIDOWS_JS)
                check(f"no one-word last lines on the gallery [{tag}] {widows[:3]}", not widows)
                if not new_layout:
                    check(f"metrics is a 5-step journey ending in the north star [{tag}]",
                          page.locator("#metrics .journey li").count() == 5 and page.locator("#metrics .journey li.north").count() == 1
                          and page.locator("#metrics .metric, #metrics .flow").count() == 0 and page.locator("#metrics .watch > div").count() == 2)
                    check(f"metrics stays short (under 90 words incl. emoji and heading, was 126) [{tag}]", len(txt(page, "#metrics").split()) < 90)
                if label == "desktop":
                    nav_fits = page.evaluate("""[...document.querySelectorAll('.mb-links a')].every(a => { const r = a.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.width > 0; })
                        && document.querySelector('.mb-links').scrollWidth <= document.querySelector('.mb-links').clientWidth + 1""")
                    check(f"every nav link is on screen, no sideways scroll [{tag}]", nav_fits)
                else:
                    check(f"phone: sections sit behind the menu button [{tag}]",
                          page.is_visible(".mb-menu") and not page.is_visible(".mb-links a"))
                if shots:
                    page.screenshot(path=os.path.join(shots, f"gallery-{scheme}-{label}.png"), full_page=True)

                clicky = data["clickys"][0]
                page.goto(home + "?c=" + clicky["slug"])
                page.wait_for_selector("h1")
                body = txt(page, "body")
                for part in (clicky["name"], clicky["routine"]["label"], clicky["shared_by"],
                             str(clicky["estimated_agent_messages_per_month"])):
                    check(f"A2 detail shows '{part}' [{tag}]", part in body)
                check(f"A2 setup box holds exact setup [{tag}]", page.input_value("textarea.setup") == clicky["setup_text"])
                page.evaluate("document.fonts.ready")
                widows = page.evaluate(WIDOWS_JS)
                check(f"no one-word last lines on the detail page [{tag}] {widows[:3]}", not widows)
                page.click("button:has-text('Copy setup')")
                page.wait_for_function("document.querySelector('.status').textContent.length > 0")
                clipboard = page.evaluate("navigator.clipboard.readText()")
                check(f"A4 clipboard gets exact setup [{tag}]", clipboard == clicky["setup_text"])
                check(f"A4 copy confirms [{tag}]", "Copied" in txt(page, ".status"))
                no_scroll = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                check(f"A5 no horizontal scroll on detail [{tag}]", no_scroll)
                button_height = page.locator("button:has-text('Copy setup')").bounding_box()["height"]
                check(f"A5 Copy button tappable (>=44px) [{tag}]", button_height >= 44)
                text_color = page.evaluate("getComputedStyle(document.body).color")
                background = page.evaluate("getComputedStyle(document.body).backgroundColor")
                check(f"A6 text and background differ [{tag}]", text_color != background)
                ratios = page.evaluate(CONTRAST_JS, DETAIL_SMALL_TEXT)
                check(f"A6 small text contrast >= 4.5 on detail (min {min(ratios):.2f}) [{tag}]", min(ratios) >= 4.5)
                check(f"invite note explains the discount [{tag}]",
                      (page.locator(".invite-note").count() == 1) == bool(clicky["invite_url"]))
                if shots:
                    page.screenshot(path=os.path.join(shots, f"detail-{scheme}-{label}.png"), full_page=True)

                check(f"Needs Pro note on a Clicky over the Free limit [{tag}]",
                      (clicky["share_of_plan_percent"]["free"] > 100) == (page.locator(".needs-pro").count() == 1))
                check(f"Mac-only note present [{tag}]", page.locator(".mac-note").count() == 1)

                page.goto(home + "?c=" + clicky["name"].replace(" ", "%20"))
                page.wait_for_selector("h1")
                check(f"name in URL resolves like the connector [{tag}]", txt(page, "h1") == clicky["name"])

                page.goto(home + "?c=" + "x" * 90)
                page.wait_for_selector("h1")
                no_scroll = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                check(f"A5 long unknown slug does not cause horizontal scroll [{tag}]", no_scroll)

                page.goto(home + "?c=does-not-exist")
                page.wait_for_selector("h1")
                check(f"A3 unknown slug shows not found [{tag}]", "No shared Clicky called" in txt(page, "h1"))
                check(f"A3 link back to gallery [{tag}]", page.locator("a.btn[href='./']").count() == 1)

                check(f"no console errors [{tag}]", not errors)
                context.close()

        context = browser.new_context()
        page = context.new_page()
        page.goto(broken_base + PAGE)
        page.wait_for_selector("h1")
        check("load error state when data missing", "Couldn't load" in txt(page, "h1"))
        context.close()

        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(home + "?c=" + data["clickys"][0]["slug"])
        page.wait_for_selector("button:has-text('Copy setup')")
        page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
        page.click("button:has-text('Copy setup')")
        selected = page.evaluate("window.getSelection().toString() || (document.activeElement && document.activeElement.value.substring(document.activeElement.selectionStart, document.activeElement.selectionEnd))")
        check("A4 fallback selects setup text when clipboard unavailable", selected == data["clickys"][0]["setup_text"])
        check("A4 fallback tells user to press Cmd+C", "press ⌘C" in txt(page, ".status"))
        check("A4 fallback styled as a warning", "warn" in page.get_attribute(".status", "class"))
        page.goto(home)
        page.wait_for_selector("#connector button")
        page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
        page.click("#connector button")
        check("connector URL fallback really selects the URL",
              page.evaluate("window.getSelection().toString()") == data["connector_url"])
        context.close()

        for clicky in data["clickys"]:
            context = browser.new_context()
            page = context.new_page()
            page.goto(base + "c/" + clicky["slug"] + "/")
            page.wait_for_url("**/?c=" + clicky["slug"])
            page.wait_for_selector("h1")
            check(f"share link /c/{clicky['slug']}/ forwards to its detail view", txt(page, "h1") == clicky["name"])
            context.close()
        # Phone sizes: one-row top bar, one-line kicker, working sections menu, no one-word lines.
        for width in (320, 360, 375, 390, 393, 402, 414, 430):
            context = browser.new_context(viewport={"width": width, "height": 800}, is_mobile=True, has_touch=True)
            route_fonts(context)
            page = context.new_page()
            page.goto(home)
            page.wait_for_selector(".card")
            page.evaluate("document.fonts.ready")
            bar = page.evaluate("""(() => {
                const shown = [...document.querySelectorAll('.wordmark, .radio, .gh, .mb-menu')].filter(e => e.offsetWidth).map(e => e.getBoundingClientRect());
                const apart = shown.every((r, i) => i === 0 || r.left >= shown[i - 1].right);
                const k = document.querySelector('.kicker'), line = parseFloat(getComputedStyle(k).fontSize) * 1.8;
                return { oneRow: document.querySelector('.menubar').getBoundingClientRect().height < 60, apart, inside: shown.every(r => r.left >= 0 && r.right <= innerWidth),
                         kickerOneLine: k.getBoundingClientRect().height < line + 14 && k.getBoundingClientRect().right <= innerWidth };
            })()""")
            widows = page.evaluate(WIDOWS_JS)
            check(f"phone {width}px: top bar one row, nothing overlaps, kicker on one line, no one-word lines {bar} {widows[:2]}",
                  all(bar.values()) and not widows)
            page.tap(".mb-menu")
            page.wait_for_timeout(250)
            opened = page.evaluate("""[...document.querySelectorAll('.mb-links a')].every(a => { const r = a.getBoundingClientRect(); return r.width > 0 && r.left >= 0 && r.right <= innerWidth && r.height >= 40; })""")
            check(f"phone {width}px: menu shows all 8 sections, on screen, easy to tap", opened and page.locator(".mb-links a").count() == 8)
            if width == 390:
                check("phone: menu button says it is open", page.get_attribute(".mb-menu", "aria-expanded") == "true")
                page.tap(".mb-links a[href$='#metrics']")
                page.wait_for_timeout(900)
                closed = not page.evaluate("document.querySelector('.menubar').classList.contains('open')")
                landed = abs(page.evaluate("document.getElementById('metrics').getBoundingClientRect().top") - 64) < 30
                check("phone: tapping a section closes the menu and lands on it", closed and landed)
                page.tap(".mb-menu"); page.wait_for_timeout(200)
                page.keyboard.press("Escape"); page.wait_for_timeout(200)
                check("phone: Escape closes the menu", not page.evaluate("document.querySelector('.menubar').classList.contains('open')"))
                page.tap(".mb-menu"); page.wait_for_timeout(200)
                page.tap("#metrics h2"); page.wait_for_timeout(200)
                check("phone: tapping outside closes the menu", not page.evaluate("document.querySelector('.menubar').classList.contains('open')"))
            context.close()
        browser.close()

    server.shutdown()
    broken_server.shutdown()
    print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
