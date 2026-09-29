"""Builds the one-page v2 preview at docs/v2/index.html from the live docs/index.html.

The live page is never modified. v2 = the live page with the approved content
restructure applied (6 sections, story order, each idea said once), served from
/share-a-clicky/v2/ with shared media referenced through "../".

Run: python3 tools/make_v2_preview.py
Promote later (only after Mohit approves): python3 tools/make_v2_preview.py --promote
  which writes the same page to docs/index.html with root paths and no preview ribbon.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "docs", "index.html")
OUT_PREVIEW = os.path.join(ROOT, "docs", "v2", "index.html")

src = open(LIVE, encoding="utf-8").read()
page = src


def replace_once(old, new):
    global page
    count = page.count(old)
    if count != 1:
        sys.exit(f"expected exactly one match, found {count}: {old[:90]!r}")
    page = page.replace(old, new)


def replace_between(start, end, new):
    """Replace from `start` (inclusive) up to `end` (exclusive)."""
    global page
    a = page.index(start)
    b = page.index(end, a)
    page = page[:a] + new + page[b:]


# ---------- nav: 6 links in story order ----------
replace_between('<nav class="mb-links" aria-label="Sections">', "</nav>",
    '<nav class="mb-links" aria-label="Sections">\n'
    '      <a href="./#demo">demo</a><a href="./#shared">clickys</a><a href="./#connector">connector</a>'
    '<a href="./#idea">why</a><a href="./#findings">findings</a><a href="./#builder">about me</a>\n    ')

# ---------- page body: the 6 sections ----------
NEW_BODY = r'''    app.replaceChildren(
      // ---- 1. hero: what it is, the demo, who built it ----
      el("div", { class: "hero" }, [
        el("span", { class: "sticker tile", style: "left:3%;top:40px;--r:-10deg", "aria-hidden": "true", text: "💼" }),
        el("span", { class: "sticker tile", style: "right:5%;top:70px;--r:8deg;animation-delay:-2s", "aria-hidden": "true", text: "📬" }),
        el("span", { class: "sticker tag", style: "right:4%;top:170px;--r:-6deg;animation-delay:-1s", "aria-hidden": "true", text: "shared by @mohit" }),
        el("span", { class: "sticker live", style: "left:2%;top:205px;--r:-4deg;animation-delay:-2.5s", "aria-hidden": "true", text: "tested live ✓" }),
        el("span", { class: "drag-hint", style: "left:2%;top:172px", "aria-hidden": "true", text: "psst, drag these anywhere ↓" }),
        el("div", { class: "kicker" }, [el("span", { class: "dot", "aria-hidden": "true" }), "an unofficial product bet for HeyClicky, built and tested live"]),
        el("h1", {}, [el("span", { class: "line", text: "start with a clicky" }), " ", el("span", { class: "line" }, ["that ", el("mark", { class: "hl", text: "already works" })])]),
        el("p", { class: "sub", text: "Share a Clicky you've set up for a real job. A friend pastes its setup into HeyClicky and starts from something that already works. Your invite link comes along." }),
        el("div", { class: "cta" }, [
          el("a", { class: "btn", href: "#shared", text: "Browse shared Clickys" }),
          el("a", { class: "btn secondary", href: "#connector", text: "Add the connector" })
        ]),
        el("p", { class: "byline" }, ["Built by Mohit Malviya, AI product manager who builds · ", el("a", { href: "#builder", text: "about me ↓" })]),
        demoPlayer()
      ]),

      // ---- 2. try it ----
      el("section", { id: "shared" }, [
        sectionHead("shared clickys", "pick one, copy, paste", "Job Hunter is the one I use for my own job search. The other two are examples. Each shows its monthly agent messages, so you know before installing if it needs Pro."),
        el("ol", { class: "steps-line reveal", id: "how", "aria-label": "How it works" }, [
          el("li", {}, [el("b", { text: "1" }), " Open a Clicky"]),
          el("li", {}, [el("b", { text: "2" }), " Copy setup"]),
          el("li", {}, [el("b", { text: "3" }), " In HeyClicky, click + and paste"])
        ]),
        el("div", { class: "grid" }, data.clickys.map(clickyCard))
      ]),

      // ---- 3. proof it works inside the real app ----
      el("section", { id: "connector" }, [
        sectionHead("inside heyclicky", "works inside heyclicky today", "Add the connector once. Then any Clicky can list shared Clickys and hand over a setup."),
        el("div", { class: "panel narrow reveal" }, [
          el("ol", { class: "howto", style: "margin-top:0" }, [
            el("li", {}, [el("span", { class: "num", "aria-hidden": "true", text: "1" }), el("div", { class: "body" }, [
              el("span", { text: "In HeyClicky, open" }),
              el("div", { class: "path" }, [
                el("span", { class: "kbd", text: "Settings" }), el("span", { class: "sep", "aria-hidden": "true", text: "›" }),
                el("span", { class: "kbd", text: "Integrations" }), el("span", { class: "sep", "aria-hidden": "true", text: "›" }),
                el("span", { class: "kbd", text: "Add custom connector" })
              ])
            ])]),
            el("li", {}, [el("span", { class: "num", "aria-hidden": "true", text: "2" }), el("div", { class: "body" }, [
              el("span", {}, ["Paste this as the Server URL and set Authentication to ", el("span", { class: "kbd", text: "None" })]),
              el("div", { class: "term" }, [
                el("div", { class: "term-bar", "aria-hidden": "true" }, [el("i", { style: "background:#ff5f57" }), el("i", { style: "background:#febc2e" }), el("i", { style: "background:#28c840" }), el("span", { text: "connector.url" })]),
                el("div", { class: "term-body" }, [el("span", { class: "prompt", "aria-hidden": "true", text: "$" }), connectorCode, copyConnector])
              ]),
              connectorStatus
            ])]),
            el("li", {}, [el("span", { class: "num", "aria-hidden": "true", text: "3" }), el("div", { class: "body" }, [
              el("span", { text: "In any Clicky, ask" }), el("br"),
              el("span", { class: "ask", text: "What shared Clickys can I get?" })
            ])])
          ]),
          el("figure", { class: "proof" }, [
            el("img", { src: "img/hero-window.webp", alt: "A HeyClicky chat listing three shared Clickys, then handing over the Weekly Wins setup to paste into New Clicky", width: "1200", height: "1295", loading: "lazy", decoding: "async" }),
            el("figcaption", { text: "Live on HeyClicky 1.0.52 through this connector. My other Clickys are hidden." })
          ])
        ])
      ]),

      // ---- 4. the product thinking ----
      el("section", { id: "idea" }, [
        sectionHead("the idea", "why I built it"),
        el("div", { class: "why-list reveal" }, [
          el("div", {}, [el("span", { class: "badge", "aria-hidden": "true", text: "🧩" }), el("div", {}, [el("b", { text: "The gap" }),
            el("span", { text: "A new Clicky starts from four onboarding questions or a short interview. You can't start from one a friend already runs." })])]),
          el("div", {}, [el("span", { class: "badge", "aria-hidden": "true", text: "🎯" }), el("div", {}, [el("b", { text: "The bet" }),
            el("span", { text: "A Clicky from someone you trust, for a job they really have, is a stronger first Clicky. It sits next to HeyClicky's own suggestions." })])]),
          el("div", {}, [el("span", { class: "badge", "aria-hidden": "true", text: "🚀" }), el("div", {}, [el("b", { text: "Why now" }),
            el("span", { text: "Invite & Earn (Sep 24) gives people a reason to share. A shared Clicky gives the invite link something specific to carry." })])])
        ])
      ]),

      // ---- 5. what shipping it taught me, and how I'd measure it ----
      el("section", { id: "findings" }, [
        sectionHead("found while testing it live", "what I found, and how I'd measure it", "Three things I only learned by shipping it into the real app. Then the numbers I'd watch."),
        el("div", { class: "findings" }, [
          el("div", { class: "finding reveal" }, [el("span", { class: "k", text: "bug" }), el("b", { text: "Local connectors stop at message 2" }), el("span", { text: "A local connector (“Command on this Mac”) answers once, then fails with “Transport closed.” I built the web connector to get around it. The real fix is inside HeyClicky: keep the local session open." })]),
          el("div", { class: "finding reveal" }, [el("span", { class: "k", text: "missing hook" }), el("b", { text: "A Clicky can't create a Clicky" }), el("span", { text: "So install is one paste, not one click. A create_clicky tool or a heyclicky://new link would close the gap." })]),
          el("div", { class: "finding reveal" }, [el("span", { class: "k", text: "upgrade moment" }), el("b", { text: "Daily routines need Pro" }), el("span", { text: "Job Hunter uses about 30 agent messages a month, more than Free's 25. Saying so up front beats a surprise limit." })])
        ]),
        el("div", { class: "measure reveal", id: "metrics" }, [
          el("p", { class: "north" }, [el("b", { text: "North star " }), "Shared Clickys still running a week after install, vs Clickys made in onboarding."]),
          el("ol", { class: "funnel" }, [
            funnelStep("Views to copies", "does the page make people want it?", 100),
            funnelStep("Copies to created", "does the paste work?", 82),
            funnelStep("Created to routine on", "a separate step today, likely the biggest drop", 64),
            funnelStep("Invite signups", "new users per shared Clicky", 46),
            funnelStep("Free to Pro", "within 14 days of a “needs Pro” install", 30)
          ]),
          el("p", { class: "guard" }, [el("b", { text: "Guardrails " }), "Fewer surprise agent-limit hits, and few shared Clickys archived or reported in week one. Tracking needs one “installed from a share” tag. No real data yet, this is the plan."])
        ])
      ]),

      // ---- 6. who built it, plus quick questions ----
      el("section", { id: "builder" }, [
        sectionHead("who built this", "about me"),
        el("div", { class: "note-card reveal" }, [
          el("div", { class: "win-bar", "aria-hidden": "true" }, [el("i", { style: "background:#ff5f57" }), el("i", { style: "background:#febc2e" }), el("i", { style: "background:#28c840" }), el("span", { text: "note-from-mohit.txt" })]),
          el("div", { class: "note-body" }, [
            el("div", { class: "avatar", "aria-hidden": "true", text: "MM" }),
            el("div", {}, [
              el("h3", { text: "Mohit Malviya" }),
              el("div", { class: "roles" }, [el("span", { class: "role", text: "AI product manager who builds" }), el("span", { class: "role alt", text: "Cornell MBA" })]),
              el("p", { text: "6.5 years in product management, most recently leading the beta of an AI triage agent in Jira during a PM internship at Atlassian. Computer science engineering degree, first job writing code as a full-stack product engineer at Wipro, and a fresh Cornell MBA in AI, Tech & Product Management." }),
              el("p", { text: "Think growth product engineer with product management depth. Share-a-Clicky shows how I work. Find the gap, make a bet, build it end to end, test it live, and know how to measure it." }),
              el("p", { text: "Based in NYC. Open to remote, and happy to fly out to SF whenever it helps." }),
              el("div", { class: "skills" }, ["product discovery", "metrics", "AI agents", "MCP", "Cloudflare Workers", "Python", "JavaScript", "testing"].map(function (s) { return el("span", { text: s }); })),
              el("div", { class: "sig", "aria-hidden": "true", text: "mohit" }),
              el("div", { class: "note-links" }, [
                el("a", { href: "mailto:mohit.malviya.cornell@gmail.com", text: "Email me" }),
                el("a", { href: "https://www.linkedin.com/in/malviyamohit/", rel: "noopener", text: "LinkedIn" }),
                el("a", { class: "alt", href: "https://github.com/Mohit-Malviya-AI-PM/share-a-clicky", rel: "noopener", text: "Code on GitHub" })
              ])
            ])
          ])
        ]),
        el("div", { class: "faq", id: "faq" }, [
          el("h3", { class: "faq-title", text: "quick questions" }),
          el("details", { class: "reveal" }, [el("summary", { text: "Is this made by HeyClicky?" }), el("p", { text: "No. It's an unofficial prototype I built on my own to show how sharing could work. It isn't affiliated with or endorsed by HeyClicky." })]),
          el("details", { class: "reveal" }, [el("summary", { text: "Does installing one use agent messages?" }), el("p", { text: "Making a Clicky on the New Clicky page doesn't use a credit. Its routine does. Every shared Clicky shows roughly how many agent messages its routine uses a month, and says “needs Pro” when that's more than Free's 25." })]),
          el("details", { class: "reveal" }, [el("summary", { text: "Is it safe to paste a setup?" }), el("p", { text: "A setup is instructions for an agent that can reach your apps, so read it first. The full text is on the page before you copy it, and these setups never send email without asking. A real version should also list the apps and actions a setup touches, and review shared ones." })]),
          el("details", { class: "reveal" }, [el("summary", { text: "Where's the code?" }), el("p", { text: "On GitHub, MIT licensed, with the tests and a full log of what I tested live." })])
        ])
      ])
    );

    setupReveal();
    enableStickers();
    enablePlayer();
    trackSections();
  }

  function funnelStep(title, why, width) {
    return el("li", {}, [
      el("span", { class: "fbar", style: "width:" + width + "%", "aria-hidden": "true" }),
      el("b", { text: title }), el("span", { text: why })
    ]);
  }
'''
replace_between("    app.replaceChildren(\n      // ---- hero ----", "  function metric(title, why, width) {", NEW_BODY)
# the rotator and marquee helpers are no longer used
replace_once('    var rotating = el("b", { text: "job hunting" });\n', "")
page = re.sub(r'    var marqueeItems = \[.*?\n    function marqueeRow\(\) \{.*?\n', "", page, count=1)

# ---------- no per-section stickers (decoration stays in the hero) ----------
replace_between("  var SECTION_STICKERS = {", "  function decorateSections() {", "  var SECTION_STICKERS = {};\n")

# ---------- styles for the new pieces ----------
NEW_CSS = r'''
  /* ---- v2 layout ---- */
  .byline { margin: 14px auto 0; font-size: 14px; color: var(--text-3); }
  .byline a { font-weight: 600; }
  .hero .demo { margin-top: 28px; }
  .steps-line { list-style: none; padding: 0; margin: 0 auto 18px; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
  .steps-line li { display: inline-flex; align-items: center; gap: 8px; background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 7px 14px 7px 7px; font-size: 14.5px; font-weight: 500; box-shadow: var(--shadow-sm); }
  .steps-line b { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 12.5px; }
  .why-list { max-width: 760px; margin: 0 auto; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow-sm); }
  .why-list > div { display: grid; grid-template-columns: 44px 1fr; gap: 14px; align-items: start; padding: 18px 20px; }
  .why-list > div + div { border-top: 1px solid var(--line); }
  .why-list .badge { display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 14px; font-size: 22px; background: var(--surface-2); }
  .why-list b { display: block; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 2px; }
  .why-list span { color: var(--text-2); font-size: 15px; }
  .measure { max-width: 760px; margin: 22px auto 0; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 20px; }
  .measure .north { margin: 0 0 14px; font-size: 15.5px; }
  .measure .guard { margin: 14px 0 0; font-size: 14px; color: var(--text-2); }
  .funnel { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .funnel li { position: relative; padding: 8px 0 12px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 0 8px; align-items: baseline; }
  .funnel li::after { content: ""; position: absolute; left: 0; right: 0; bottom: 2px; height: 5px; border-radius: 999px; background: var(--surface-2); }
  .funnel .fbar { position: absolute; left: 0; bottom: 2px; height: 5px; border-radius: 999px; background: linear-gradient(90deg, var(--sky), var(--mint)); z-index: 1; }
  .funnel b { font-weight: 600; }
  .funnel span { color: var(--text-2); }
  .faq { margin-top: 28px; }
  @media (max-width: 640px) {
    section { padding-top: 52px; }
    .section-head { margin-bottom: 20px; }
    .card { display: grid; grid-template-columns: 44px 1fr; column-gap: 12px; padding: 16px; }
    .card .emoji { width: 44px; height: 44px; font-size: 24px; margin: 0; grid-row: span 2; }
    .card h3 { margin: 0; align-self: center; }
    .card p { margin: 2px 0 0; }
    .card .meta { grid-column: 1 / -1; margin-top: 10px; }
    .finding { padding: 18px 18px 20px; }
    .note-body { padding: 20px 20px 22px; gap: 12px; }
    .note-body .avatar { width: 48px; height: 48px; font-size: 17px; }
    .note-body .sig { display: none; }
  }
  .faq-title { margin: 0 0 4px; text-align: center; font-size: 17px; font-weight: 600; letter-spacing: -0.01em; }
'''
replace_once("</style>", NEW_CSS + "</style>")
open_marker = page  # noqa


def preview(p):
    """Paths for /v2/: shared files live one level up. Adds noindex and a preview ribbon."""
    p = p.replace('href="img/', 'href="../img/')
    p = p.replace('src: "img/', 'src: "../img/').replace('poster: "img/', 'poster: "../img/')
    p = p.replace('"media/', '"../media/')
    p = p.replace('fetch("clickys.json"', 'fetch("../clickys.json"')
    p = p.replace("url(img/", "url(../img/")
    p = p.replace('<meta name="viewport"', '<meta name="robots" content="noindex">\n<meta name="viewport"', 1)
    p = p.replace("<title>share-a-clicky</title>", "<title>share-a-clicky (preview)</title>", 1)
    p = p.replace('document.title = "share-a-clicky";', 'document.title = "share-a-clicky (preview)";', 1)
    p = p.replace("</style>", "  .preview-ribbon { position: fixed; left: 50%; bottom: 12px; transform: translateX(-50%); z-index: 60; background: #16161a; color: #fff; font: 600 12.5px/1 Inter, system-ui, sans-serif; padding: 8px 12px; border-radius: 999px; box-shadow: 0 10px 24px -10px rgba(0,0,0,.5); white-space: nowrap; pointer-events: none; }\n</style>", 1)
    p = p.replace("<body>", '<body>\n<div class="preview-ribbon" aria-hidden="true">preview · new one-page layout · live site unchanged</div>', 1)
    return p


if "--promote" in sys.argv:
    open(LIVE, "w", encoding="utf-8").write(page)
    print("promoted v2 layout to docs/index.html")
else:
    os.makedirs(os.path.dirname(OUT_PREVIEW), exist_ok=True)
    open(OUT_PREVIEW, "w", encoding="utf-8").write(preview(page))
    print("wrote docs/v2/index.html")
