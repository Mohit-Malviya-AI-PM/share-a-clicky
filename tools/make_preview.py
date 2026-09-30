"""Stage docs/index.html as a review copy at docs/preview/index.html.

The copy lives one folder down, so shared files are referenced through "../".
It is marked noindex and shows a small "preview" label. The live page is not touched.
Run: python3 tools/make_preview.py [source_html]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "index.html")
out = os.path.join(ROOT, "docs", "preview", "index.html")
p = open(src, encoding="utf-8").read()
p = p.replace('href="img/', 'href="../img/').replace('src: "img/', 'src: "../img/').replace('poster: "img/', 'poster: "../img/')
p = p.replace('"media/', '"../media/').replace('fetch("clickys.json"', 'fetch("../clickys.json"').replace("url(img/", "url(../img/")
p = p.replace('<meta name="viewport"', '<meta name="robots" content="noindex">\n<meta name="viewport"', 1)
p = p.replace("</style>", "  .preview-ribbon { position: fixed; left: 50%; bottom: 12px; transform: translateX(-50%); z-index: 60; background: #16161a; color: #fff; font: 600 12.5px/1 Inter, system-ui, sans-serif; padding: 8px 12px; border-radius: 999px; box-shadow: 0 10px 24px -10px rgba(0,0,0,.5); white-space: nowrap; pointer-events: none; }\n</style>", 1)
p = p.replace("<body>", '<body>\n<div class="preview-ribbon" aria-hidden="true">preview · fixes to review · live site unchanged</div>', 1)
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write(p)
print("wrote", os.path.relpath(out, ROOT))
