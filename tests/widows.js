// Finds text blocks whose last line holds a single word (a "widow").
// Returns [{where, last, tail}] for every visible block of running text.
// Skips code, the setup text box, the connector URL and decorative bits.
() => {
  const SKIP = "script,style,textarea,.code,.term-body,svg,.np-bars,#tiles,.marquee,.vp-cap,.vp-ring,.sticker,.drag-hint,.kaomoji,.np-toast,noscript,.preview-ribbon";
  const INLINE = new Set(["inline"]);
  function label(e) {
    let s = e.tagName.toLowerCase();
    if (e.id) s += "#" + e.id;
    if (e.className && typeof e.className === "string") s += "." + e.className.trim().split(/\s+/).join(".");
    const sec = e.closest("section[id], .hero, header, footer, figure");
    return (sec && sec !== e ? (sec.id ? "#" + sec.id : sec.className ? "." + String(sec.className).split(" ")[0] : sec.tagName.toLowerCase()) + " > " : "") + s;
  }
  const out = [];
  document.querySelectorAll("body *").forEach((e) => {
    if (e.closest(SKIP)) return;
    const cs = getComputedStyle(e);
    if (INLINE.has(cs.display) || cs.display === "none" || cs.visibility === "hidden" || cs.display === "contents") return;
    const r0 = e.getBoundingClientRect();
    if (!r0.width || !r0.height) return;
    if (e.closest("details:not([open])") && !e.closest("summary")) return;
    const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (!n.textContent.trim()) return NodeFilter.FILTER_REJECT;
        for (let p = n.parentElement; p && p !== e; p = p.parentElement) {
          if (!INLINE.has(getComputedStyle(p).display)) return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const words = [];
    while (walker.nextNode()) {
      const n = walker.currentNode, re = /[^\s]+/g;
      let m;
      while ((m = re.exec(n.textContent))) {
        const r = document.createRange();
        r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const rects = r.getClientRects();
        if (!rects.length) continue;
        words.push({ w: m[0], top: rects[rects.length - 1].top, first: rects[0].top });
      }
    }
    if (words.length < 3) return;
    const last = words[words.length - 1], prev = words[words.length - 2];
    const tops = new Set(words.map((x) => Math.round(x.top / 4)));
    if (tops.size < 2) return;
    if (last.top - prev.top > 4 || last.first !== last.top) {
      out.push({ where: label(e), last: last.w, tail: e.innerText.replace(/\s+/g, " ").trim().slice(-70) });
    }
  });
  return out;
};
