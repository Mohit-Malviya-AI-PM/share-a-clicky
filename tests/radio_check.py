"""End-to-end checks for mohit's radio and the demo video player on phones and desktop.

Run: python3 tests/radio_check.py [chromium] [webkit]

Headless Chromium and WebKit via Playwright, with touch input. Phone behaviour that
headless browsers don't do on their own is simulated with small init scripts:
  android        volume works, radio fades under the video
  android-focus  the browser pauses the radio when the video starts (audio focus)
  iphone-strict  volume is read-only, the video pauses other audio, and sound may only
                 start inside a tap (the harshest phone rule)
  webkit         the Safari engine, real mp4 demo video
Covers: tap to play, music really advancing, duck and resume around the demo video,
the video's tap-to-show-controls behaviour, next / previous / auto-advance,
lock-screen pause, rapid taps, bad files, stalled downloads.
"""
import functools, http.server, os, threading, sys, time
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP radio tests: install with `pip install playwright && playwright install chromium webkit`")
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
WEBM = os.path.join(ROOT, "tests", "fixtures", "demo-test.webm")  # Chromium in Playwright can't play H.264


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, *a):
        pass  # browsers drop media downloads mid-file; not a failure


srv = Server(("127.0.0.1", 0), functools.partial(Quiet, directory=SITE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"

CAPTURE = """(()=>{const A=window.Audio;window.__aud=[];
window.Audio=function(...a){const x=new A(...a);window.__aud.push(x);return x};window.Audio.prototype=A.prototype;})();"""
READONLY_VOLUME = "Object.defineProperty(HTMLMediaElement.prototype,'volume',{get(){return 1},set(v){},configurable:true});"
# When the demo video starts with sound, the browser pauses other audio (iPhone, some Android).
FOCUS = """document.addEventListener('play', e => { if (e.target.tagName !== 'VIDEO' || e.target.muted) return;
  (window.__aud||[]).forEach(a => { if (!a.paused) a.pause(); }); }, true);"""
# play() is only allowed while a tap's click event is being handled.
STRICT = """(()=>{window.__inClick=false;
addEventListener('click',()=>{window.__inClick=true;setTimeout(()=>window.__inClick=false,0)},true);
['play','pause','ended','volumechange','playing','timeupdate'].forEach(n=>document.addEventListener(n,()=>{window.__inClick=false},true));
const P=HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play=function(){ if(!window.__inClick) return Promise.reject(new DOMException('needs a tap','NotAllowedError')); return P.call(this); };})();"""

MODES = {
    "chromium": [("android", ""), ("android-focus", FOCUS), ("iphone-strict", READONLY_VOLUME + FOCUS + STRICT)],
    "webkit": [("webkit", "")],
}

fails = 0


def check(name, ok):
    global fails
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails += 1


def st(page):
    return page.get_attribute(".radio", "data-state")


def wait(page, js, timeout=15000):
    try:
        page.wait_for_function(js, timeout=timeout)
        return True
    except Exception:
        return False


def radio_playing(page):
    return page.evaluate("!window.__aud[0].paused") and st(page) == "playing"


def open_page(ctx, tag, errs, init="", route_media=None):
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.add_init_script(CAPTURE + init)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
    if route_media:
        route_media(page)
    if tag.startswith("chromium"):
        page.route("**/share-a-clicky-demo.mp4", lambda r: r.fulfill(path=WEBM, content_type="video/webm"))
    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_selector(".card")
    if tag.startswith("chromium"):
        page.evaluate("(()=>{const v=document.querySelector('#demo video'); v.querySelector('source').type='video/webm'; v.load();})()")
    return page


def center(page, sel):
    box = page.locator(sel).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.35


with sync_playwright() as p:
    for bname in (sys.argv[1:] or ["chromium", "webkit"]):
        browser = getattr(p, bname).launch(args=["--autoplay-policy=user-gesture-required"] if bname == "chromium" else [])
        for mode, init in MODES[bname]:
            tag = f"{bname}/{mode}"
            strict = mode == "iphone-strict"
            fades = mode in ("android", "webkit")
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=(bname == "chromium"), has_touch=True)
            errs = []
            page = open_page(ctx, tag, errs, init)

            # ---- radio basics ----
            check(f"off by default [{tag}]", st(page) == "off" and page.evaluate("window.__aud[0].paused"))
            check(f"no audio downloaded before tap [{tag}]", page.evaluate("window.__aud[0].getAttribute('src')") is None)
            page.tap(".np")
            check(f"tap starts music [{tag}] state={st(page)}", wait(page, "document.querySelector('.radio').dataset.state==='playing'"))
            t0 = page.evaluate("window.__aud[0].currentTime"); time.sleep(1.5); t1 = page.evaluate("window.__aud[0].currentTime")
            check(f"music is actually advancing ({t0:.2f}->{t1:.2f}) [{tag}]", t1 > t0 + 0.5)
            if fades:
                check(f"fades up to 0.55 [{tag}]", abs(page.evaluate("window.__aud[0].volume") - 0.55) < 0.02)

            # ---- video player on a touch screen ----
            page.locator("#demo").scroll_into_view_if_needed()
            page.tap("#demo .vp-big")
            check(f"big play button starts the video with sound [{tag}]",
                  wait(page, "(()=>{const v=document.querySelector('#demo video');return !v.paused && !v.muted && v.currentTime>0.2})()"))
            time.sleep(0.8)
            if fades:
                check(f"radio fades to ~0.08 under the video [{tag}] vol={page.evaluate('window.__aud[0].volume'):.3f}",
                      abs(page.evaluate("window.__aud[0].volume") - 0.0825) < 0.02 and not page.evaluate("window.__aud[0].paused"))
            else:
                check(f"radio steps aside under the video [{tag}] state={st(page)}",
                      page.evaluate("window.__aud[0].paused") and st(page) == "ducked")
            check(f"controls hide after 3s of playing [{tag}]", wait(page, "document.querySelector('#demo .vp').classList.contains('idle')", 6000))
            x, y = center(page, "#demo video")
            page.touchscreen.tap(x, y)
            time.sleep(0.9)
            check(f"first tap on a playing video shows controls, keeps playing [{tag}]",
                  page.evaluate("!document.querySelector('#demo .vp').classList.contains('idle') && !document.querySelector('#demo video').paused"))
            page.touchscreen.tap(x, y)
            time.sleep(0.4)
            check(f"second tap pauses the video [{tag}]", page.evaluate("document.querySelector('#demo video').paused"))
            check(f"radio comes back when the video is paused by a tap [{tag}] state={st(page)}",
                  wait(page, "document.querySelector('.radio').dataset.state==='playing' && !window.__aud[0].paused", 3000))
            if fades:
                check(f"radio back to 0.55 [{tag}]", wait(page, "Math.abs(window.__aud[0].volume-0.55)<0.02", 3000))
            time.sleep(3.5)
            check(f"controls stay up while paused [{tag}]", not page.evaluate("document.querySelector('#demo .vp').classList.contains('idle')"))
            page.tap("#demo .vp-play")
            time.sleep(0.9)
            check(f"bar play button plays and the bar stays up [{tag}]",
                  page.evaluate("!document.querySelector('#demo video').paused && !document.querySelector('#demo .vp').classList.contains('idle')"))
            check(f"radio steps aside again [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='ducked' || Math.abs(window.__aud[0].volume-0.0825)<0.02", 3000))
            page.tap("#demo .vp-play")
            time.sleep(0.4)
            check(f"bar pause button pauses [{tag}]", page.evaluate("document.querySelector('#demo video').paused"))
            check(f"radio comes back after the bar pause button [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='playing' && !window.__aud[0].paused", 3000))
            page.tap("#demo .vp-play")
            time.sleep(0.8)
            # video stops without a tap (end of video, keyboard, lock screen)
            page.evaluate("document.querySelector('#demo video').pause()")
            time.sleep(1)
            if strict:
                check(f"no tap: radio waits instead of turning off [{tag}] state={st(page)}", st(page) == "ducked")
                page.tap("#faq h2") if page.locator("#faq h2").count() else page.tap("footer")
                check(f"next tap anywhere brings the radio back [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='playing' && !window.__aud[0].paused", 3000))
            else:
                check(f"radio comes back when the video stops on its own [{tag}] state={st(page)}",
                      wait(page, "document.querySelector('.radio').dataset.state==='playing' && !window.__aud[0].paused", 3000))

            # ---- radio controls ----
            page.tap(".np-skip")
            check(f"next song plays [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('funky-chunk')"))
            page.tap(".np-prev")
            check(f"previous song plays [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('hustle')"))
            if not strict:
                page.evaluate("window.__aud[0].playbackRate=16")
                check(f"auto-advances at song end [{tag}]", wait(page, "window.__aud[0].currentSrc.includes('funky-chunk') && !window.__aud[0].paused", 30000))
            page.tap(".np")
            time.sleep(0.6)
            check(f"tap pauses [{tag}]", page.evaluate("window.__aud[0].paused") and st(page) == "off")
            page.tap(".np")
            check(f"tap resumes [{tag}]", wait(page, "document.querySelector('.radio').dataset.state==='playing'", 10000))
            page.evaluate("window.__aud[0].pause()")
            time.sleep(0.3)
            check(f"lock-screen pause syncs the button [{tag}]", st(page) == "off")
            for _ in range(7):
                page.tap(".np")
            time.sleep(1.5)
            check(f"odd number of rapid taps leaves it playing [{tag}]", st(page) in ("playing", "loading") and not page.evaluate("window.__aud[0].paused"))

            # ---- failures ----
            p2 = open_page(ctx, tag, errs, init, lambda pg: pg.route(lambda u: "/media/radio-" in u, lambda r: r.fulfill(status=404, body="nope")))
            p2.tap(".np")
            wait(p2, "document.querySelector('.radio').dataset.state==='off'", 45000)
            check(f"all files broken: chip stays, shows message [{tag}]",
                  st(p2) == "off" and p2.is_visible(".np") and ("couldn't" in p2.inner_text(".np-toast") or (strict and "Tap radio" in p2.inner_text(".np-toast"))))
            if not strict:
                p3 = open_page(ctx, tag, errs, init, lambda pg: pg.route(lambda u: "/media/radio-hustle" in u, lambda r: r.abort()))
                p3.tap(".np")
                check(f"stalled download moves on to the next song [{tag}]",
                      wait(p3, "document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('funky-chunk')", 35000))
            check(f"no page errors [{tag}] {errs}", not errs)
            ctx.close()

        # desktop mouse: a click on the video still toggles right away
        if bname == "chromium":
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            errs = []
            page = open_page(ctx, "chromium/desktop", errs)
            page.locator("#demo").scroll_into_view_if_needed()
            page.click("#demo .vp-big")
            wait(page, "!document.querySelector('#demo video').paused && document.querySelector('#demo video').currentTime>0.2")
            page.mouse.move(*center(page, "#demo video"))
            page.mouse.click(*center(page, "#demo video"))
            time.sleep(0.3)
            check("desktop: one click on the video pauses it", page.evaluate("document.querySelector('#demo video').paused"))
            page.mouse.click(*center(page, "#demo video"))
            time.sleep(0.3)
            check("desktop: next click plays it", not page.evaluate("document.querySelector('#demo video').paused"))
            ctx.close()
        browser.close()

print("FAILS:", fails)
sys.exit(1 if fails else 0)
