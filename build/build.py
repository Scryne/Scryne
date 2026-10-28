"""Build the profile SVGs: every panel in a dark and a light file, all text as outlines.

    python build/build.py            # draw from build/data/contributions.json
    python build/build.py --fetch    # refresh that file from the public contribution calendar first

The calendar is read from the public page (the same numbers a visitor sees under the README), so the hero never
claims more than the profile shows. Colours come from the DESIGN.md frontmatter.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import io
import json
import math
import re
import urllib.request
from pathlib import Path

import uharfbuzz as hb
import yaml
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ROOT / "build" / "fonts"
DATA = ROOT / "build" / "data" / "contributions.json"
USER = "Scryne"
WINDOW_DAYS = 182


def num(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# --- type -----------------------------------------------------------------------------------------------------------


GLYPHS: dict[tuple[str, str], tuple[str, str]] = {}  # (font, glyph) -> (id, outline), current file


class Font:
    def __init__(self, file: str, wght: int | None = None):
        tt = TTFont(FONTS / file)
        if wght is not None:
            tt = instancer.instantiateVariableFont(tt, {"wght": wght})
        buf = io.BytesIO()
        tt.save(buf)
        data = buf.getvalue()
        self.name = file
        self.tt = TTFont(io.BytesIO(data))
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.cmap = self.tt.getBestCmap()
        self.upem = self.tt["head"].unitsPerEm
        self.hb = hb.Font(hb.Face(data))

    def _shape(self, text: str):
        missing = sorted({c for c in text if not c.isspace() and ord(c) not in self.cmap})
        if missing:
            raise SystemExit(f"{self.name}: no glyph for {missing!r}")
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True, "calt": False})
        return list(zip(buf.glyph_infos, buf.glyph_positions))

    def width(self, text: str, size: float, track: float = 0.0) -> float:
        items = self._shape(text)
        s = size / self.upem
        return sum(p.x_advance for _, p in items) * s + track * size * max(len(items) - 1, 0)

    def _glyph(self, name: str) -> str | None:
        """Id of the glyph's outline in the current file's <defs>, or None for an empty glyph like a space."""
        key = (self.name, name)
        if key not in GLYPHS:
            pen = SVGPathPen(self.glyphs, ntos=num)
            self.glyphs[name].draw(pen)
            GLYPHS[key] = (f"g{len(GLYPHS)}", pen.getCommands())
        gid, d = GLYPHS[key]
        return gid if d else None

    def uses(self, text: str, size: float, x: float, y: float, track: float = 0.0, anchor: str = "start") -> str:
        """The text as <use> references to glyph outlines, so each outline is written once per file."""
        items = self._shape(text)
        s = size / self.upem
        x -= {"start": 0.0, "middle": 0.5, "end": 1.0}[anchor] * self.width(text, size, track)
        out = []
        for info, pos in items:
            gid = self._glyph(self.order[info.codepoint])
            if gid:
                out.append(f'<use href="#{gid}" transform="matrix({s:.5g} 0 0 {-s:.5g} '
                           f'{num(x + pos.x_offset * s)} {num(y - pos.y_offset * s)})"/>')
            x += pos.x_advance * s + track * size
        return "".join(out)


SERIF = Font("InstrumentSerif-Regular.ttf")
ITALIC = Font("InstrumentSerif-Italic.ttf")
MONO = Font("JetBrainsMono[wght].ttf", 500)
MONO_B = Font("JetBrainsMono[wght].ttf", 700)


def text(font: Font, s: str, size: float, x: float, y: float, fill: str, track: float = 0.0,
         anchor: str = "start", attrs: str = "") -> str:
    return f'<g fill="{fill}"{" " + attrs if attrs else ""}>{font.uses(s, size, x, y, track, anchor)}</g>'


def label(s: str, x: float, y: float, fill: str, size: float = 13, anchor: str = "start", bold: bool = False) -> str:
    return text(MONO_B if bold else MONO, s.upper(), size, x, y, fill, 0.14, anchor)


def text_on_circle(font: Font, s: str, size: float, cx: float, cy: float, r: float, fill: str) -> str:
    """Set s around a full circle, tracking stretched so it closes on itself."""
    widths = [font.width(c, size) for c in s]
    gap = (2 * math.pi * r - sum(widths)) / len(s)
    out, a = [], 0.0
    for c, w in zip(s, widths):
        mid = a + w / 2
        if not c.isspace():
            deg = math.degrees(mid / r)
            out.append(f'<g transform="translate({num(cx)} {num(cy)}) rotate({deg:.2f})">'
                       f'{font.uses(c, size, 0, -r, anchor="middle")}</g>')
        a += w + gap
    return f'<g fill="{fill}">{"".join(out)}</g>'


# --- themes and frame -----------------------------------------------------------------------------------------------


def themes() -> list[dict]:
    meta = yaml.safe_load((ROOT / "DESIGN.md").read_text(encoding="utf-8").split("---")[1])
    c, g = meta["colors"], meta["glass"]
    out = []
    for name, pre in [("dark", ""), ("light", "light-")]:
        k = lambda key: c[pre + key]  # noqa: E731
        dials = dict(g[name])
        # Objects drawn on the glass (receipt, pages, tiles) are tinted glass too, not opaque blocks.
        rgb = ",".join(str(int(k("surface")[i:i + 2], 16)) for i in (1, 3, 5))
        bg = f"rgba({rgb},{dials.pop('surface')})"
        out.append(dict(name=name, base=k("base"), bg=bg, edge=k("edge"), grid2=k("rivet"),
                        blobs=[k("blob-1"), k("blob-2"), k("blob-3")], ink=k("ink"), ink2=k("ink-2"),
                        ink3=k("ink-3"), accent=k("accent"), metal=(k("metal-hi"), k("metal-lo")),
                        glow=name == "dark", **dials))
    return out


REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}.motion{display:none}}"


def svg(w: int, h: int, title: str, desc: str, body: str, style: str = "") -> str:
    defs = "".join(f'<path id="{gid}" d="{d}"/>' for gid, d in GLYPHS.values() if d)
    GLYPHS.clear()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-labelledby="t d"><title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>'
            f"<style>{style}{REDUCED}</style><defs>{defs}</defs>{body}</svg>\n")


# Mesh layouts as fractions of the panel: (cx, cy, rx, ry, blob). Light falls from the top left in all of them.
MESHES = [
    [(.12, .05, .55, .7, 0), (.85, .45, .45, .6, 1), (.35, 1.05, .6, .45, 2)],
    [(.05, .2, .5, .8, 0), (.7, .0, .5, .5, 1), (.9, 1.0, .5, .6, 2)],
    [(.25, -.05, .6, .55, 0), (1.0, .7, .45, .7, 1), (.0, .95, .5, .5, 2)],
    [(.0, .0, .45, .9, 0), (.55, .9, .6, .45, 1), (1.0, .2, .4, .6, 2)],
]


def frame(t: dict, w: int, h: int, mesh: int = 0) -> str:
    """A glass panel: blurred silver mesh behind, a frosted sheen on top, a rim that catches light at the top left."""
    box = f'x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18"'
    hi, lo = t["metal"]
    blobs = "".join(f'<ellipse cx="{num(cx * w)}" cy="{num(cy * h)}" rx="{num(rx * w)}" ry="{num(ry * h)}" '
                    f'fill="{t["blobs"][i]}" fill-opacity="{t["mesh"][i]}"/>' for cx, cy, rx, ry, i in MESHES[mesh % 4])
    return (f'<defs><clipPath id="clip"><rect {box}/></clipPath>'
            f'<filter id="soft" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{num(min(w, h) * .16)}"/></filter>'
            f'<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="#fff" stop-opacity="{t["sheen"][0]}"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity="{t["sheen"][1]}"/></linearGradient>'
            f'<linearGradient id="rim" x1="0" y1="0" x2=".6" y2="1">'
            f'<stop offset="0" stop-color="#fff" stop-opacity="{t["rim"][0]}"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity="{t["rim"][1]}"/></linearGradient>'
            f'<linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{hi}"/><stop offset="1" stop-color="{lo}"/></linearGradient></defs>'
            f'<rect {box} fill="{t["base"]}"/>'
            f'<g clip-path="url(#clip)"><g filter="url(#soft)">{blobs}</g></g>'
            f'<rect {box} fill="url(#sheen)"/>'
            f'<rect {box} fill="none" stroke="{t["edge"]}"/>'
            f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="17" fill="none" stroke="url(#rim)"/>')


def glass(t: dict, x: float, y: float, w: float, h: float, rx: float = 10) -> str:
    """A smaller pane of the same glass, for readout boxes and chips."""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="#fff" fill-opacity="{t["pane"]}" '
            f'stroke="url(#rim)"/>')


def glow_filter(t: dict) -> str:
    if not t["glow"]:
        return ""
    return ('<filter id="glow" x="-10%" y="-50%" width="120%" height="200%">'
            '<feGaussianBlur stdDeviation="5"/></filter>')


# --- data -----------------------------------------------------------------------------------------------------------


def fetch() -> None:
    req = urllib.request.Request(f"https://github.com/users/{USER}/contributions",
                                 headers={"User-Agent": "Mozilla/5.0 (profile build)"})
    page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    cells = {}
    for tag in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", page):
        date, cid = re.search(r'data-date="([\d-]+)"', tag), re.search(r'id="([^"]+)"', tag)
        if date and cid:
            cells[cid.group(1)] = date.group(1)
    days = {}
    for cid, tip in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        if cid in cells:
            m = re.match(r"\s*([\d,]+) contribution", tip)
            days[cells[cid]] = int(m.group(1).replace(",", "")) if m else 0
    if len(days) < 300:
        raise SystemExit(f"calendar parse looks wrong: {len(days)} days")
    DATA.write_text(json.dumps({"fetched": dt.date.today().isoformat(), "days": sorted(days.items())}, indent=0),
                    encoding="utf-8")


def load() -> tuple[list[tuple[str, int]], str]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return [(d, int(n)) for d, n in raw["days"]], raw["fetched"]


# --- hero: the scope screen -----------------------------------------------------------------------------------------


def smooth_path(pts: list[tuple[float, float]], floor: float) -> str:
    """Catmull-Rom through the points as cubic Béziers, never dipping below the baseline."""
    d = [f"M{num(pts[0][0])} {num(pts[0][1])}"]
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(p1[1] + (p2[1] - p0[1]) / 6, floor))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(p2[1] - (p3[1] - p1[1]) / 6, floor))
        d.append(f"C{num(c1[0])} {num(c1[1])} {num(c2[0])} {num(c2[1])} {num(p2[0])} {num(p2[1])}")
    return "".join(d)


def hero(t: dict, days: list[tuple[str, int]], fetched: str) -> str:
    W, H = 1200, 484
    X0, X1, BASE, AMP = 40, 1160, 428, 128
    win = days[-WINDOW_DAYS:]
    vals = [n for _, n in win]
    sm = [sum(vals[max(i - 1, 0):i + 2]) / len(vals[max(i - 1, 0):i + 2]) for i in range(len(vals))]
    top = max(max(sm), 1) * 1.06
    step = (X1 - X0) / (len(sm) - 1)
    pts = [(X0 + i * step, BASE - v / top * AMP) for i, v in enumerate(sm)]
    line = smooth_path(pts, BASE)
    area = f"{line}L{X1} {BASE}L{X0} {BASE}Z"

    total = sum(n for _, n in days)
    last30 = sum(n for _, n in days[-30:])
    best = max(days, key=lambda x: x[1])
    a, ink, ink2, ink3 = t["accent"], t["ink"], t["ink2"], t["ink3"]

    style = (".draw{stroke-dasharray:1;animation:draw 2.6s cubic-bezier(.65,0,.25,1) .2s backwards}"
             "@keyframes draw{from{stroke-dashoffset:1}}"
             ".fade{animation:fade 1.2s ease 2s backwards}@keyframes fade{from{opacity:0}}"
             ".blink{animation:blink 1.8s steps(1) infinite}@keyframes blink{50%{opacity:.15}}")
    b = [frame(t, W, H, 0)]
    b.append(f'<defs>{glow_filter(t)}<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{a}" stop-opacity="{.2 if t["glow"] else .22}"/>'
             f'<stop offset="1" stop-color="{a}" stop-opacity="0"/></linearGradient>'
             f'<linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">'
             f'<stop offset="0" stop-color="{ink3}"/><stop offset=".55" stop-color="{a}"/>'
             f'<stop offset="1" stop-color="{t["metal"][0]}"/></linearGradient></defs>')

    # header strip
    b.append(f'<path d="M1 56H{W - 1}" stroke="url(#rim)"/>')
    b.append(f'<circle class="blink" cx="38" cy="28" r="5" fill="{a}"/>')
    b.append(label("live", 52, 33, a, bold=True))
    b.append(label("ch1 · contributions per day", 112, 33, ink2))
    b.append(label(f"{WINDOW_DAYS // 7} wk window · updated {fetched}", W - 36, 33, ink3, anchor="end"))

    # wordmark and motto
    b.append(text(SERIF, "Scryne", 172, 44, 200, ink, -0.01))
    b.append(text(ITALIC, "AI-assisted software, measured before it is trusted.", 34, 50, 270, ink2))

    # measurement box, as on a scope's side panel
    bx, by, bw, rh = 880, 84, 280, 50
    rows = [("total · 1 yr", f"{total:,}"), ("last 30 days", f"{last30:,}"), ("best day", f"{best[1]:,}")]
    b.append(glass(t, bx, by, bw, rh * len(rows), 12))
    for i, (k, v) in enumerate(rows):
        y = by + rh * i
        if i:
            b.append(f'<path d="M{bx + 12} {y}H{bx + bw - 12}" stroke="{ink3}" stroke-opacity=".3"/>')
        b.append(label(k, bx + 18, y + 30, ink3, 12))
        b.append(text(MONO_B, v, 24, bx + bw - 18, y + 34, "url(#metal)", anchor="end"))

    # time axis: a tick per week, a longer tick and a label per month
    ticks, labels = [], []
    for i, (d, _) in enumerate(win):
        x = X0 + i * step
        day = dt.date.fromisoformat(d)
        if day.day == 1:
            ticks.append(f"M{num(x)} {BASE}v10")
            labels.append(label(day.strftime("%b"), x + 5, BASE + 26, ink3, 12))
        elif day.weekday() == 0:
            ticks.append(f"M{num(x)} {BASE}v4")
    guides = "".join(f"M{X0} {BASE - AMP * f}H{X1}" for f in (.25, .5, .75, 1))
    b.append(f'<path d="{guides}" stroke="{ink3}" stroke-opacity=".18" stroke-dasharray="2 6"/>')
    b.append(f'<path d="M{X0} {BASE}H{X1}{"".join(ticks)}" stroke="{ink3}" fill="none"/>')
    b.extend(labels)

    # the trace
    b.append(f'<path class="fade" d="{area}" fill="url(#fill)"/>')
    if t["glow"]:
        b.append(f'<path class="draw" pathLength="1" d="{line}" fill="none" stroke="{a}" stroke-width="6" '
                 f'stroke-opacity=".35" filter="url(#glow)"/>')
    b.append(f'<path class="draw" pathLength="1" d="{line}" fill="none" stroke="url(#beam)" stroke-width="2.2" '
             f'stroke-linejoin="round" stroke-linecap="round"/>')
    b.append(f'<g class="motion" opacity="0"><set attributeName="opacity" to="1" begin="2.9s"/>'
             f'<circle r="11" fill="{a}" opacity=".18"/><circle r="4.5" fill="{a}"/>'
             f'<animateMotion dur="8s" begin="2.9s" repeatCount="indefinite" path="{line}"/></g>')

    desc = (f"A glass oscilloscope-style panel. The trace is {USER}'s contributions per day over the last "
            f"{WINDOW_DAYS // 7} weeks: {total:,} in the past year, {last30:,} in the last 30 days, best day "
            f"{best[1]:,} on {best[0]}.")
    return svg(W, H, "Scryne: AI-assisted software, measured before it is trusted.", desc, "".join(b), style)


# --- project cards --------------------------------------------------------------------------------------------------


def bars(rows, fill, opacity=".55") -> str:
    return "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" fill-opacity="{opacity}"/>'
                   for x, y, w, h in rows)


def g_citefield(t: dict) -> str:
    a, ink, ink2, ink3, bg = t["accent"], t["ink"], t["ink2"], t["ink3"], t["bg"]
    teeth = "".join("l-8 8l-8 -8" for _ in range(10))
    o = [f'<path d="M30 6H190V232{teeth}Z" fill="{bg}" stroke="{ink3}" stroke-linejoin="round"/>',
         bars([(76, 26, 68, 8)], ink2, ".7"),
         bars([(48, 58 + 20 * i, w, 7) for i, w in enumerate([84, 62, 96, 54, 74, 88])], ink3),
         bars([(152, 58 + 20 * i, 22, 7) for i in range(6)], ink3),
         f'<path d="M48 186H174" stroke="{ink3}" stroke-dasharray="3 3"/>',
         bars([(48, 200, 50, 9)], ink2, ".8"), bars([(146, 200, 28, 9)], ink2, ".8"),
         f'<rect class="draw" pathLength="1" x="140" y="194" width="40" height="21" rx="3" fill="{a}" '
         f'fill-opacity=".14" stroke="{a}" stroke-width="1.8"/>',
         f'<rect class="draw" pathLength="1" x="144" y="72" width="34" height="19" rx="3" fill="none" '
         f'stroke="{a}" stroke-width="1.4" stroke-dasharray="4 3" style="animation-delay:.5s"/>',
         f'<path class="draw" pathLength="1" d="M180 204.5H226V176H262" fill="none" stroke="{a}" stroke-width="1.4" '
         f'style="animation-delay:.9s"/>',
         f'<path class="draw" pathLength="1" d="M178 81.5H226V96H262" fill="none" stroke="{a}" stroke-width="1.4" '
         f'stroke-dasharray="4 3" style="animation-delay:1.1s"/>']
    for y, k, v, ok in [(150, "total", "41.90", True), (70, "line 2", "12.50", False)]:
        o.append(glass(t, 262, y, 196, 54, 8))
        if ok:
            o.append(f'<rect x="262" y="{y}" width="196" height="54" rx="8" fill="none" stroke="{a}" '
                     f'stroke-opacity=".7"/>')
        o.append(label(k, 278, y + 21, ink3, 11))
        o.append(text(MONO_B, v, 21, 278, y + 43, ink))
        if ok:
            o.append(f'<path d="M424 {y + 28}l6 6l12 -13" fill="none" stroke="{a}" stroke-width="2.4" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
        else:
            o.append(label("review", 442, y + 43, a, 11, "end", True))
    return "".join(o)


def g_tenderiq(t: dict) -> str:
    a, ink2, ink3, bg = t["accent"], t["ink2"], t["ink3"], t["bg"]
    o = []
    for dx, dy in [(28, 0), (14, 8)]:
        o.append(f'<rect x="{dx}" y="{dy}" width="112" height="148" rx="4" fill="{bg}" stroke="{ink3}" '
                 f'stroke-opacity=".7"/>')
    o.append(f'<path d="M0 18H90L112 40V166H0Z" fill="{bg}" stroke="{ink3}" stroke-linejoin="round"/>'
             f'<path d="M90 18V40H112" fill="none" stroke="{ink3}"/>')
    o.append(bars([(12, 32, 52, 7)], ink2, ".7"))
    o.append(bars([(12, 52 + 14 * i, w, 6) for i, w in enumerate([86, 74, 90, 0, 64, 84, 0, 80])  if w], ink3))
    o.append(f'<rect class="draw" pathLength="1" x="8" y="91" width="96" height="14" rx="2" fill="{a}" '
             f'fill-opacity=".18" stroke="{a}" stroke-width="1.6"/>')
    o.append(f'<path class="draw" pathLength="1" d="M104 98H138" stroke="{a}" stroke-width="1.4" '
             f'style="animation-delay:.6s"/>')
    o.append(f'<circle cx="158" cy="98" r="20" fill="{bg}" stroke="{a}" stroke-width="1.8"/>')
    o.append(text(SERIF, "§", 28, 158, 107, a, anchor="middle"))
    o.append(label("p.14", 158, 140, ink2, 11, "middle"))
    return "".join(o)


def g_ghost(t: dict) -> str:
    a, ink, ink3, bg = t["accent"], t["ink"], t["ink3"], t["bg"]
    o = []
    city = ('<path d="M0 18H56M0 40H56M20 0V56M40 0V56" stroke="{s}" stroke-width="3" stroke-opacity=".35"/>'
            '<rect x="4" y="4" width="12" height="10" fill="{s}" fill-opacity=".6"/>'
            '<rect x="24" y="22" width="12" height="14" fill="{s}" fill-opacity=".6"/>'
            '<rect x="44" y="44" width="10" height="9" fill="{s}" fill-opacity=".6"/>'
            '<rect x="24" y="44" width="12" height="8" fill="{s}" fill-opacity=".6"/>')
    for i, name in enumerate(["esri", "maptiler", "ign"]):
        x = i * 62
        o.append(f'<g transform="translate({x} 8)"><rect width="56" height="56" rx="3" fill="{bg}" stroke="{ink3}"/>'
                 + city.format(s=ink3))
        if i == 0:
            cells = "".join(f'<rect x="{2 + c * 13}" y="{2 + r * 13}" width="13" height="13" fill="{ink3}" '
                            f'fill-opacity="{[.55, .3, .45, .2][(r * 3 + c) % 4]}"/>'
                            for r in range(4) for c in range(4))
            o.append(f'<g class="flicker">{cells}</g><rect width="56" height="56" rx="3" fill="none" stroke="{a}" '
                     f'stroke-width="2"/>')
        o.append("</g>")
        o.append(label(name, x + 28, 84, a if i == 0 else ink3, 10, "middle", i == 0))
    o.append(label("score", 0, 116, ink3, 11))
    o.append(text(MONO_B, "88.9", 16, 180, 117, a, anchor="end"))
    o.append(f'<rect x="0" y="128" width="180" height="6" rx="3" fill="{ink3}" fill-opacity=".25"/>'
             f'<rect class="grow" x="0" y="128" width="{180 * .889:.0f}" height="6" rx="3" fill="{a}"/>'
             f'<path d="M90 124V138" stroke="{ink}" stroke-width="1.4"/>')
    o.append(label("p99 line", 90, 156, ink3, 10, "middle"))
    return "".join(o)


def g_myth(t: dict) -> str:
    a, ink2, ink3 = t["accent"], t["ink2"], t["ink3"]
    cx, cy, r = 90, 84, 78
    o = [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ink3}" stroke-opacity=".6"/>']
    for rx in (26, 54):
        o.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{r}" fill="none" stroke="{ink3}" stroke-opacity=".3"/>')
    for dy in (-40, 0, 40):
        hw = math.sqrt(r * r - dy * dy)
        o.append(f'<path d="M{num(cx - hw)} {cy + dy}H{num(cx + hw)}" stroke="{ink3}" stroke-opacity=".3"/>')
    stars = [(42, 58), (70, 40), (104, 62), (128, 44), (118, 104), (78, 112), (54, 132)]
    o.append(f'<path d="M{" L".join(f"{x} {y}" for x, y in stars[:5])} M{stars[2][0]} {stars[2][1]} '
             f'L{stars[5][0]} {stars[5][1]} L{stars[6][0]} {stars[6][1]}" fill="none" stroke="{ink2}" '
             f'stroke-opacity=".7"/>')
    o.extend(f'<circle cx="{x}" cy="{y}" r="3" fill="{ink2}"/>' for x, y in stars if (x, y) != stars[2])
    x, y = stars[2]
    o.append(f'<circle class="pulse" cx="{x}" cy="{y}" r="11" fill="none" stroke="{a}" stroke-width="1.4"/>'
             f'<circle cx="{x}" cy="{y}" r="5" fill="{a}"/>')
    return "".join(o)


def g_wartrack(t: dict) -> str:
    a, ink3 = t["accent"], t["ink3"]
    cx, cy = 90, 84
    o = [f'<defs><linearGradient id="sweep" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}" '
         f'stop-opacity=".35"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></linearGradient></defs>']
    for r in (28, 54, 80):
        o.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ink3}" stroke-opacity=".55"/>')
    o.append(f'<path d="M{cx - 80} {cy}H{cx + 80}M{cx} {cy - 80}V{cy + 80}" stroke="{ink3}" stroke-opacity=".35"/>')
    end = (cx + 80 * math.cos(math.radians(-50)), cy + 80 * math.sin(math.radians(-50)))
    o.append(f'<g class="motion"><path d="M{cx} {cy}L{cx + 80} {cy}A80 80 0 0 0 {num(end[0])} {num(end[1])}Z" '
             f'fill="url(#sweep)"/><path d="M{cx} {cy}H{cx + 80}" stroke="{a}" stroke-width="1.6"/>'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" '
             f'dur="5s" repeatCount="indefinite"/></g>')
    for x, y, r in [(122, 60, 4.5), (64, 46, 3), (52, 112, 3.5), (130, 114, 2.5), (100, 128, 3)]:
        o.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{a}"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{t["ink2"]}"/>')
    return "".join(o)


def g_gridgrade(t: dict) -> str:
    a, ink2, ink3, bg = t["accent"], t["ink2"], t["ink3"], t["bg"]
    heights = [46, 62, 38, 80, 54, 96, 70, 44, 58]
    o = [label("¢/kwh", 0, 10, ink3, 10)]
    for i, h in enumerate(heights):
        hot = i == 5
        o.append(f'<rect class="rise" x="{i * 20}" y="{100 - h}" width="13" height="{h}" rx="2" '
                 f'fill="{a if hot else ink3}" fill-opacity="{1 if hot else .45}"/>')
    o.append(f'<path d="M0 100.5H176" stroke="{ink3}"/>')
    for i, g in enumerate("ABCDF"):
        x, on = i * 36, g == "B"
        o.append(f'<rect x="{x}" y="118" width="30" height="30" rx="4" fill="{a if on else bg}" '
                 f'stroke="{a if on else ink3}"/>')
        o.append(text(MONO_B, g, 16, x + 15, 139, bg if on else ink2, anchor="middle"))
    return "".join(o)


def g_kokpit(t: dict) -> str:
    a, ink2, ink3, bg = t["accent"], t["ink2"], t["ink3"], t["bg"]
    o = [f'<rect x="0" y="4" width="180" height="148" rx="8" fill="{bg}" stroke="{ink3}"/>'
         f'<path d="M0 24H180" stroke="{ink3}" stroke-opacity=".6"/>']
    o.extend(f'<circle cx="{12 + i * 11}" cy="14" r="3" fill="{ink3}" fill-opacity=".7"/>' for i in range(3))
    panes = [(8, 32), (94, 32), (8, 94), (94, 94)]
    for i, (x, y) in enumerate(panes):
        on = i == 1
        o.append(f'<rect x="{x}" y="{y}" width="78" height="54" rx="4" fill="none" '
                 f'stroke="{a if on else ink3}" stroke-opacity="{1 if on else .45}" stroke-width="{1.6 if on else 1}"/>')
        o.append(text(MONO_B, "›", 12, x + 7, y + 17, a if on else ink3))
        o.append(bars([(x + 18, y + 10, [44, 30, 50, 36][i], 6), (x + 7, y + 24, [30, 52, 22, 40][i], 5)], ink3, ".5"))
        if on:
            o.append(f'<rect class="blink" x="{x + 7}" y="{y + 36}" width="8" height="11" fill="{a}"/>')
    return "".join(o)


CARDS = [
    dict(key="citefield", url="https://github.com/Scryne/citefield", kicker="01 — document ai", title="Citefield",
         desc=["Self-hosted invoice and receipt extraction where", "every value points to the words it was read from."],
         note="measured · cord v2 receipts · citefield eval",
         readouts=[("88.7%", "values right"), ("96.3%", "box on the right words"), ("0.8%", "errors, auto-approved")],
         glyph=g_citefield,
         alt="Citefield: self-hosted document extraction. 88.7% of values right, 96.3% boxed on the right words, "
             "0.8% errors among auto-approved values on CORD v2 receipts."),
    dict(key="tenderiq", url="https://github.com/Scryne/TenderIQ", kicker="02 — tender analysis", title="TenderIQ",
         desc=["A finding without its source", "is rejected, not shown."],
         readout=("p.14 §3.2", ["every finding carries", "document, page, clause"]), glyph=g_tenderiq,
         alt="TenderIQ: citation-first analysis of public tender documents; every finding carries document, page "
             "and clause."),
    dict(key="ghostbuilding", url="https://github.com/Scryne/GhostBuilding", kicker="03 — osint · imagery",
         title="GhostBuilding", desc=["Three satellite providers,", "one calibrated baseline."],
         readout=("3 / 20", ["sensitive sites flagged", "0 of 7 controls"]), glyph=g_ghost,
         alt="GhostBuilding: compares three satellite imagery providers; 3 of 20 sensitive sites flagged, 0 of 7 "
             "controls."),
    dict(key="mythatlas", url="https://github.com/Scryne/MythAtlas", kicker="04 — open data · maps",
         title="MythAtlas", desc=["Myths, deities and sacred sites,", "checked against Wikidata."],
         readout=("1,826→274", ["citations kept after", "the integrity gate"]), glyph=g_myth,
         alt="MythAtlas: an atlas of myths, deities and sacred sites; citations went from 1,826 to 274 after the "
             "integrity gate."),
    dict(key="wartrack", url="https://github.com/Scryne/Wartrack", kicker="05 — monitoring", title="Wartrack",
         desc=["Regional monitoring board,", "summarized by a local model."],
         readout=("15 → 1", ["news feeds into one", "explainable threat level"]), glyph=g_wartrack,
         alt="Wartrack: regional monitoring board; 15 news feeds into one explainable threat level."),
    dict(key="gridgrade", url="https://github.com/Scryne/gridgrade", kicker="06 — data site", title="GridGrade",
         desc=["US electricity prices and", "utility report cards."],
         readout=("A–F", ["utilities graded,", "rebuilt daily from EIA data"]), glyph=g_gridgrade,
         alt="GridGrade: US electricity prices and utility report cards graded A to F, rebuilt daily from EIA data."),
    dict(key="kokpit", url="https://github.com/Scryne/Kokpit", kicker="07 — dev tools", title="Kokpit",
         desc=["A desktop cockpit for", "AI-assisted development."],
         readout=("1 click", ["from the project board", "to Claude Code"]), glyph=g_kokpit,
         alt="Kokpit: desktop cockpit for AI-assisted development; one click from the project board to Claude Code."),
]

CARD_STYLE = (".draw{stroke-dasharray:1;animation:draw 1.4s cubic-bezier(.65,0,.25,1) .3s backwards}"
              "@keyframes draw{from{stroke-dashoffset:1}}"
              ".blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
              ".flicker{animation:flicker 3.2s steps(1) infinite}"
              "@keyframes flicker{40%{opacity:1}42%{opacity:.4}44%{opacity:1}80%{opacity:.7}82%{opacity:1}}"
              ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite}"
              "@keyframes pulse{from{transform:scale(.5);opacity:1}to{transform:scale(1.6);opacity:0}}"
              ".grow{transform-box:fill-box;transform-origin:left;animation:grow 1.4s cubic-bezier(.65,0,.25,1) "
              ".3s backwards}@keyframes grow{from{transform:scaleX(0)}}"
              ".rise{transform-box:fill-box;transform-origin:bottom;animation:rise 1s cubic-bezier(.65,0,.25,1) "
              ".2s backwards}@keyframes rise{from{transform:scaleY(0)}}")


def arrow(t: dict, x: float, y: float) -> str:
    return (f'<path d="M{x} {y + 14}L{x + 14} {y}M{x + 4} {y}H{x + 14}V{y + 10}" fill="none" stroke="{t["ink3"]}" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')


def card(t: dict, c: dict) -> str:
    W, H = 600, 340
    ink, ink2, ink3, a = t["ink"], t["ink2"], t["ink3"], t["accent"]
    b = [frame(t, W, H, c["mesh"]), arrow(t, W - 48, 34), label(c["kicker"], 34, 50, ink3)]
    size = 60 if SERIF.width(c["title"], 60) < 330 else 330 / SERIF.width(c["title"], 1)
    b.append(text(SERIF, c["title"], size, 32, 128, ink, -0.01))
    for i, line in enumerate(c["desc"]):
        b.append(text(MONO, line, 15, 34, 170 + 22 * i, ink2))
    b.append(f'<g transform="translate(392 70)">{c["glyph"](t)}</g>')
    b.append(f'<path d="M34 256H{W - 34}" stroke="{ink3}" stroke-opacity=".5" stroke-dasharray="2 4"/>')
    value, lines = c["readout"]
    b.append(text(MONO_B, value, 34, 34, 308, "url(#metal)"))
    lx = 34 + MONO_B.width(value, 34) + 20
    for i, line in enumerate(lines):
        b.append(label(line, lx, 293 + 19 * i, ink2, 12))
    return svg(W, H, c["title"], c["alt"], "".join(b), CARD_STYLE)


def card_wide(t: dict, c: dict) -> str:
    W, H = 1200, 340
    ink, ink2, ink3, a = t["ink"], t["ink2"], t["ink3"], t["accent"]
    b = [frame(t, W, H, c["mesh"]), arrow(t, W - 48, 34), label(c["kicker"], 34, 50, ink3)]
    b.append(text(SERIF, c["title"], 84, 30, 142, ink, -0.01))
    for i, line in enumerate(c["desc"]):
        b.append(text(MONO, line, 17, 34, 186 + 25 * i, ink2))
    b.append(f'<g transform="translate(680 48)">{c["glyph"](t)}</g>')
    b.append(f'<path d="M34 244H620" stroke="{ink3}" stroke-opacity=".5" stroke-dasharray="2 4"/>')
    for i, (value, line) in enumerate(c["readouts"]):
        x = 34 + i * 200
        b.append(text(MONO_B, value, 36, x, 292, "url(#metal)"))
        b.append(label(line, x, 316, ink2, 11))
    b.append(label(c["note"], 34, 236, ink3, 10))
    return svg(W, H, c["title"], c["alt"], "".join(b), CARD_STYLE)


# --- rating plate ---------------------------------------------------------------------------------------------------


PLATE_ROWS = [
    ("input", "model-written first drafts"),
    ("output", "what survived tests, benchmarks and real data"),
    ("built with", "Python · TypeScript · FastAPI · Next.js · React · Node"),
    ("", "PostgreSQL · pgvector · PostGIS · Redis · Celery · Electron"),
    ("ai", "Claude Code · LangGraph · hybrid retrieval · Ollama · evals"),
    ("checked by", "pytest · Vitest · Playwright · mypy · Ruff · gitleaks · CI"),
]


def plate(t: dict) -> str:
    W, H = 1200, 400
    ink, ink2, ink3, a, edge = t["ink"], t["ink2"], t["ink3"], t["accent"], t["edge"]
    style = (".stamp{transform-box:fill-box;transform-origin:center;"
             "animation:stamp .5s cubic-bezier(.3,1.6,.6,1) .6s backwards}"
             "@keyframes stamp{from{transform:scale(1.5);opacity:0}}")
    b = [frame(t, W, H, 1),
         f'<rect x="14.5" y="14.5" width="{W - 29}" height="{H - 29}" rx="10" fill="none" stroke="url(#rim)"/>']
    for x, y in [(34, 34), (W - 34, 34), (34, H - 34), (W - 34, H - 34)]:
        b.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{t["grid2"]}" stroke="{edge}"/>'
                 f'<path d="M{x - 4} {y + 2}L{x + 4} {y - 2}" stroke="{ink3}" stroke-width="1.4"/>')
    b.append(label("rating plate", 66, 76, ink2, 13, bold=True))
    b.append(label("type s-26 · ai-assisted software", 904, 76, ink3, 12, "end"))
    top, rh, x1 = 98, 42, 904
    b.append(f'<path d="M66 {top}H{x1}" stroke="{ink3}" stroke-opacity=".7"/>')
    for i, (k, v) in enumerate(PLATE_ROWS):
        y = top + rh * (i + 1)
        if k:
            b.append(label(k, 66, y - 15, ink3, 12))
        b.append(text(MONO, v, 16, 232, y - 15, ink))
        if i < len(PLATE_ROWS) - 1:
            x0 = 66 if PLATE_ROWS[i + 1][0] else 232
            b.append(f'<path d="M{x0} {y}H{x1}" stroke="{ink3}" stroke-opacity=".35"/>')
    b.append(f'<path d="M66 {top + rh * len(PLATE_ROWS)}H{x1}" stroke="{ink3}" stroke-opacity=".7"/>')
    cx, cy = 1036, 212
    b.append(f'<g class="stamp"><g transform="rotate(-12 {cx} {cy})">'
             f'<circle cx="{cx}" cy="{cy}" r="100" fill="none" stroke="{a}" stroke-width="3"/>'
             f'<circle cx="{cx}" cy="{cy}" r="86" fill="none" stroke="{a}" stroke-width="1.2"/>'
             f'<circle cx="{cx}" cy="{cy}" r="52" fill="none" stroke="{a}" stroke-width="1.2"/>'
             + text_on_circle(MONO_B, "MEASURED BEFORE IT IS TRUSTED · ", 13, cx, cy, 64, a)
             + text(SERIF, "PASS", 40, cx, cy + 10, a, 0.02, "middle")
             + label("qc", cx, cy + 32, a, 10, "middle", True)
             + "</g></g>")
    desc = "A rating plate. " + " ".join(f"{k or 'also'}: {v}." for k, v in PLATE_ROWS) + \
           " A stamp reads: measured before it is trusted, pass."
    return svg(W, H, "Rating plate", desc, "".join(b), style)


# --- main -----------------------------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="refresh the contribution calendar first")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    days, fetched = load()
    ASSETS.mkdir(exist_ok=True)
    for i, c in enumerate(CARDS):
        c["mesh"] = i
    for t in themes():
        out = {f"hero-{t['name']}.svg": hero(t, days, fetched), f"plate-{t['name']}.svg": plate(t)}
        for c in CARDS:
            out[f"card-{c['key']}-{t['name']}.svg"] = (card_wide if "readouts" in c else card)(t, c)
        for name, body in out.items():
            (ASSETS / name).write_text(body, encoding="utf-8", newline="\n")
    print(f"{len(days)} days, {sum(n for _, n in days):,} contributions, fetched {fetched}")


if __name__ == "__main__":
    main()
