"""End-to-end checks for mohit's radio (headless Chromium and WebKit via Playwright).

Run: python3 tests/radio_check.py [chromium] [webkit]
Covers: tap to play, music really advancing, fade and duck, the iPhone path
(volume is read-only there, so the radio pauses under a video and resumes after),
next / previous / auto-advance, lock-screen pause, rapid taps, bad files, stalls.
"""
import functools, http.server, os, threading, sys, time
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP radio tests: install with `pip install playwright && playwright install chromium webkit`")
    sys.exit(0)
SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, *a): pass  # browsers drop media downloads mid-file; not a failure
srv = Server(("127.0.0.1",0), functools.partial(Q, directory=SITE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"
CAPTURE = "(()=>{const A=window.Audio;window.__aud=[];window.Audio=function(...a){const x=new A(...a);window.__aud.push(x);return x};window.Audio.prototype=A.prototype;})();"
IOS = "Object.defineProperty(HTMLMediaElement.prototype,'volume',{get(){return 1},set(v){},configurable:true});"
fails = 0
BROWSERS = sys.argv[1:] or ["chromium","webkit"]
def check(name, ok):
    global fails
    print(("PASS " if ok else "FAIL ") + name)
    if not ok: fails += 1
def radio(page): return page.evaluate("window.__aud[0]") is not None
def st(page): return page.get_attribute(".radio", "data-state")
with sync_playwright() as p:
    for bname in BROWSERS:
        b = getattr(p, bname).launch(args=["--autoplay-policy=user-gesture-required"] if bname=="chromium" else [])
        for mode in (["android", "iphone-like"] if bname=="chromium" else ["webkit"]):
            tag = f"{bname}/{mode}"
            ctx = b.new_context(viewport={"width":390,"height":844}, is_mobile=(bname=="chromium"), has_touch=True)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.add_init_script(CAPTURE + (IOS if mode=="iphone-like" else ""))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
            page.goto(base, wait_until="domcontentloaded"); page.wait_for_selector(".card")
            check(f"off by default [{tag}]", st(page)=="off" and page.evaluate("window.__aud[0].paused"))
            check(f"no audio downloaded before tap [{tag}]", page.evaluate("window.__aud[0].getAttribute('src')") is None)
            page.tap(".np")
            try:
                page.wait_for_function("document.querySelector('.radio').dataset.state==='playing'", timeout=15000); ok=True
            except Exception: ok=False
            check(f"tap starts music [{tag}] state={st(page)}", ok)
            t0 = page.evaluate("window.__aud[0].currentTime"); time.sleep(1.5); t1 = page.evaluate("window.__aud[0].currentTime")
            check(f"music is actually advancing ({t0:.2f}->{t1:.2f}) [{tag}]", t1 > t0 + 0.5)
            print("   src:", page.evaluate("window.__aud[0].currentSrc").split('/')[-1], "vol:", page.evaluate("window.__aud[0].volume"))
            if mode=="android":
                time.sleep(0.5)
                check(f"fades up to 0.55 [{tag}]", abs(page.evaluate("window.__aud[0].volume")-0.55)<0.02)
            # demo video with sound
            page.evaluate("(()=>{let o=document.getElementById('other'); if(!o){o=document.createElement('audio'); o.id='other'; o.src='media/radio-funk-game-loop.mp3'; o.loop=true; document.body.appendChild(o);} o.play().catch(()=>{});})()")
            time.sleep(1.2)
            vplaying = page.evaluate("!document.getElementById('other').paused")
            if mode=="iphone-like":
                check(f"radio pauses under video (iPhone path) [{tag}] vplay={vplaying}", page.evaluate("window.__aud[0].paused") and st(page)=="ducked")
            else:
                v = page.evaluate("window.__aud[0].volume")
                check(f"radio ducks to ~0.08 under video [{tag}] vol={v:.3f} vplay={vplaying}", (abs(v-0.0825)<0.02) if mode=="android" else True)
            page.evaluate("document.getElementById('other').pause()")
            time.sleep(1.2)
            if mode=="iphone-like":
                check(f"radio resumes after video (iPhone path) [{tag}]", not page.evaluate("window.__aud[0].paused") and st(page)=="playing")
            elif mode=="android":
                check(f"radio back to 0.55 after video [{tag}]", abs(page.evaluate("window.__aud[0].volume")-0.55)<0.02)
            # skip
            page.tap(".np-skip")
            try:
                page.wait_for_function("document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('funky-chunk')", timeout=15000); ok=True
            except Exception: ok=False
            check(f"next song plays [{tag}]", ok)
            page.tap(".np-prev")
            try:
                page.wait_for_function("document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('hustle')", timeout=15000); ok=True
            except Exception: ok=False
            check(f"previous song plays [{tag}]", ok)
            # song end advances
            page.evaluate("window.__aud[0].playbackRate=16")
            try:
                page.wait_for_function("window.__aud[0].currentSrc.includes('funky-chunk') && !window.__aud[0].paused", timeout=30000); ok=True
            except Exception: ok=False
            check(f"auto-advances at song end [{tag}]", ok)
            page.tap(".np")
            time.sleep(0.6)
            check(f"tap pauses [{tag}]", page.evaluate("window.__aud[0].paused") and st(page)=="off")
            page.tap(".np")
            try:
                page.wait_for_function("document.querySelector('.radio').dataset.state==='playing'", timeout=10000); ok=True
            except Exception: ok=False
            check(f"tap resumes [{tag}]", ok)
            # external pause (lock screen)
            page.evaluate("window.__aud[0].pause()"); time.sleep(0.3)
            check(f"lock-screen pause syncs the button [{tag}]", st(page)=="off")
            # tap spam
            for _ in range(7): page.tap(".np")
            time.sleep(1.5)
            check(f"odd number of rapid taps leaves it playing [{tag}]", st(page) in ("playing","loading") and not page.evaluate("window.__aud[0].paused"))
            # broken file fallback
            page.route("**/*.m4a", lambda r: r.abort()); page.route("**/radio-hustle.mp3", lambda r: r.abort())
            page.tap(".np"); time.sleep(0.3)
            page.evaluate("window.__aud[0].removeAttribute('src')")  # force reload from hustle
            page.tap(".np")
            try:
                page.wait_for_function("document.querySelector('.radio').dataset.state==='playing'", timeout=15000); ok=True
            except Exception: ok=False
            check(f"bad file falls back to next song [{tag}] src={page.evaluate('window.__aud[0].currentSrc').split('/')[-1]}", ok)
            p2 = ctx.new_page(); p2.on("pageerror", lambda e: errs.append(str(e)))
            p2.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
            p2.route(lambda u: "/media/radio-" in u, lambda r: r.fulfill(status=404, body="nope"))
            p2.goto(base, wait_until="domcontentloaded"); p2.wait_for_selector(".card")
            p2.tap(".np"); p2.wait_for_function("document.querySelector('.radio').dataset.state==='off'", timeout=45000)
            check(f"all files broken: chip stays, shows message [{tag}] state={st(p2)} toast={p2.inner_text('.np-toast')!r}", st(p2)=="off" and p2.is_visible(".np") and "couldn't" in p2.inner_text(".np-toast"))
            p3 = ctx.new_page(); p3.add_init_script(CAPTURE)
            p3.route(lambda u: not u.startswith("http://127.0.0.1") or "/media/radio-hustle" in u, lambda r: r.abort())
            p3.goto(base, wait_until="domcontentloaded"); p3.wait_for_selector(".card")
            p3.tap(".np")
            try:
                p3.wait_for_function("document.querySelector('.radio').dataset.state==='playing' && window.__aud[0].currentSrc.includes('funky-chunk')", timeout=35000); ok=True
            except Exception: ok=False
            check(f"stalled download moves on to the next song [{tag}] state={st(p3)}", ok)
            check(f"no page errors [{tag}] {errs}", not errs)
            ctx.close()
        b.close()
print("FAILS:", fails); sys.exit(1 if fails else 0)
