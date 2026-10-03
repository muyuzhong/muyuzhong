"""Render the profile's isotherm plate and warming stripes from public contributions.

Usage: GITHUB_TOKEN=... python scripts/generate.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "muyuzhong"
OUT = Path(__file__).resolve().parent.parent / "assets"

W, H = 1200, 480
CX, CY = W / 2, H / 2
BOX = (310, 80, 64)  # half-width, half-height, corner radius of the quiet core
STEP = 6  # sampling grid for marching squares, in px
RING_GAP = 13
KOAN = ("万物趋于静止", "唯有静止本身在移动")

THEMES = {
    "dark": dict(bg="#0b0d10", ink="#e8e6df", muted="#58606b", ice="#8ec5d6", ember="#e3804f"),
    "light": dict(bg="#f2efe6", ink="#1b1f22", muted="#8c877a", ice="#2b4a5a", ember="#b4532a"),
}

# Thermal-camera "ironbow", from a cold empty day to the hottest one.
IRONBOW = ["#141824", "#1f0c48", "#4b0c80", "#8d1583", "#c6305e", "#ea5f2a",
           "#f99a1c", "#fdd25a", "#fff6d5"]

AXIOMS = [
    ("1", "世界是一切正在冷却之物的总和。"),
    ("1.1", "余温不是热的遗物，而是冷的序言。"),
    ("2", "语言是一种测温方式：它只读数，从不加热。"),
    ("3", "噪声并非信号的反面，只是尚未学会沉默的信号。"),
    ("3.1", "我等待一切静止，以便看清是什么一直在动。"),
    ("4", "时间是熵留下的签名，我在每一次提交里临摹它。"),
    ("5", "在绝对零度，记忆不再移动，于是它第一次成为真的。"),
    ("6", "答案从不抵达，它只是让问题冷却到可以被握住。"),
    ("7", ""),
]

MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,monospace"
SERIF = "'Noto Serif SC','Noto Serif CJK SC','Source Han Serif SC','Songti SC','STSong','SimSun',serif"


# ── data ──────────────────────────────────────────────────────────────

def fetch_days(login, token):
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": login},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in weeks]


# ── noise ─────────────────────────────────────────────────────────────

class Perlin:
    def __init__(self, seed):
        p = list(range(256))
        random.Random(seed).shuffle(p)
        self.p = p + p

    @staticmethod
    def _fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    @staticmethod
    def _grad(h, x, y):
        h &= 7
        u, v = (x, y) if h < 4 else (y, x)
        return (u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v)

    def noise(self, x, y):
        xi, yi = int(math.floor(x)) & 255, int(math.floor(y)) & 255
        xf, yf = x - math.floor(x), y - math.floor(y)
        u, v = self._fade(xf), self._fade(yf)
        p = self.p
        aa, ab = p[p[xi] + yi], p[p[xi] + yi + 1]
        ba, bb = p[p[xi + 1] + yi], p[p[xi + 1] + yi + 1]
        x1 = self._grad(aa, xf, yf) + u * (self._grad(ba, xf - 1, yf) - self._grad(aa, xf, yf))
        x2 = self._grad(ab, xf, yf - 1) + u * (self._grad(bb, xf - 1, yf - 1) - self._grad(ab, xf, yf - 1))
        return (x1 + v * (x2 - x1)) * 0.7

    def fbm(self, x, y, octaves=4):
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self.noise(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.1
        return total / norm


# ── geometry ──────────────────────────────────────────────────────────

def box_distance(x, y):
    hw, hh, r = BOX
    qx, qy = abs(x - CX) - hw + r, abs(y - CY) - hh + r
    outside = math.hypot(max(qx, 0), max(qy, 0))
    return outside + min(max(qx, qy), 0) - r


def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def field(perlin, heat):
    """Distance from the quiet core, warped harder the further out and the hotter it is."""
    amp = 3 + 46 * heat
    nx, ny = W // STEP + 1, H // STEP + 1
    grid = []
    for j in range(ny):
        row = []
        for i in range(nx):
            x, y = i * STEP, j * STEP
            d = box_distance(x, y)
            row.append(d + amp * smoothstep(0, 260, d) * perlin.fbm(x * 0.0045, y * 0.0045))
        grid.append(row)
    return grid


def isolines(grid, level):
    ny, nx = len(grid), len(grid[0])
    points, links = {}, {}

    def cross(key):
        if key not in points:
            kind, i, j = key
            i2, j2 = (i + 1, j) if kind == "h" else (i, j + 1)
            a, b = grid[j][i], grid[j2][i2]
            t = (level - a) / (b - a)
            points[key] = ((i + (i2 - i) * t) * STEP, (j + (j2 - j) * t) * STEP)
        return key

    def link(a, b):
        links.setdefault(cross(a), []).append(cross(b))
        links.setdefault(b, []).append(a)

    for j in range(ny - 1):
        for i in range(nx - 1):
            tl, tr = grid[j][i], grid[j][i + 1]
            br, bl = grid[j + 1][i + 1], grid[j + 1][i]
            case = (tl > level) << 3 | (tr > level) << 2 | (br > level) << 1 | (bl > level)
            if case in (0, 15):
                continue
            top, bottom = ("h", i, j), ("h", i, j + 1)
            left, right = ("v", i, j), ("v", i + 1, j)
            centre = (tl + tr + br + bl) / 4 > level
            pairs = {
                1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)],
                4: [(top, right)], 6: [(top, bottom)], 7: [(left, top)],
                8: [(left, top)], 9: [(top, bottom)], 11: [(top, right)],
                12: [(left, right)], 13: [(bottom, right)], 14: [(left, bottom)],
                5: [(left, top), (bottom, right)] if centre else [(left, bottom), (top, right)],
                10: [(top, right), (left, bottom)] if centre else [(left, top), (bottom, right)],
            }[case]
            for a, b in pairs:
                link(a, b)

    seen, chains = set(), []
    starts = [k for k, v in links.items() if len(v) == 1] + list(links)
    for start in starts:
        if start in seen:
            continue
        chain, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = next((n for n in links[cur] if n != prev and n not in seen), None)
            if nxt is None:
                if len(links[cur]) == 2 and start in links[cur] and len(chain) > 2:
                    chain.append(start)
                break
            seen.add(nxt)
            chain.append(nxt)
            prev, cur = cur, nxt
        if len(chain) > 3:
            chains.append([points[k] for k in chain])
    return chains


def simplify(pts, eps=0.45):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = 0.0, -1
        for k in range(a + 1, b):
            px, py = pts[k]
            # a closed ring starts and ends on the same point, so measure from that point
            dist = abs(dy * (px - ax) - dx * (py - ay)) / norm if norm else math.hypot(px - ax, py - ay)
            if dist > best:
                best, idx = dist, k
        if best > eps:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def densify(pts, longest=16.0):
    """Split long runs left by simplification, so Catmull-Rom does not overshoot at corners."""
    out = [pts[0]]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        parts = max(1, math.ceil(math.hypot(bx - ax, by - ay) / longest))
        out += [(ax + (bx - ax) * t / parts, ay + (by - ay) * t / parts) for t in range(1, parts + 1)]
    return out


def smooth_path(pts):
    """Catmull-Rom through the points, emitted as cubic Béziers."""
    closed = len(pts) > 3 and pts[0] == pts[-1]
    if closed:
        pts = pts[:-1]
    n = len(pts)

    def at(k):
        return pts[k % n] if closed else pts[min(max(k, 0), n - 1)]

    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    out = [f"M{f(pts[0][0])} {f(pts[0][1])}"]
    for k in range(n if closed else n - 1):
        p0, p1, p2, p3 = at(k - 1), at(k), at(k + 1), at(k + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(p2[0])} {f(p2[1])}")
    if closed:
        out.append("Z")
    return "".join(out)


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def ramp(colors, t):
    t = min(max(t, 0.0), 1.0) * (len(colors) - 1)
    k = min(int(t), len(colors) - 2)
    return mix(colors[k], colors[k + 1], t - k)


# ── plates ────────────────────────────────────────────────────────────

def frame(h):
    """Ruler ticks and corner crosses shared by the themed plates."""
    marks = []
    for x in range(40, W - 39, 20):
        long = (x - 40) % 100 == 0
        for y0, sign in ((22, 1), (h - 22, -1)):
            marks.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + sign * (7 if long else 3.5)}"/>')
    for x, y in ((40, 40), (W - 40, 40), (40, h - 40), (W - 40, h - 40)):
        marks.append(f'<path d="M{x - 6} {y}h12M{x} {y - 6}v12"/>')
    return f'<g class="inst">{"".join(marks)}</g>'


def glyphs(text, x, y, advance, cls, start, step):
    """One <text> per glyph so each arrives on its own; CJK glyphs are full width, so placement is exact."""
    return "".join(
        f'<text class="{cls}" x="{x + i * advance:.1f}" y="{y}" style="animation-delay:{start + i * step:.2f}s">{ch}</text>'
        for i, ch in enumerate(text)
    )


def isotherm_svg(theme, rings, heat, kelvin, observed, plate_no):
    c = THEMES[theme]
    n = len(rings)
    paths, labels = [], []
    for k, (level, chains) in enumerate(rings):
        u = k / max(n - 1, 1)
        colour = mix(c["ice"], c["ember"], u ** 1.4 * heat)
        index = k % 5 == 4
        width = (1.35 if index else 0.8) - 0.3 * u
        opacity = 0.95 - 0.5 * u
        draw = 0.25 + k * 0.07
        ripple = 3.4 + k * 0.09  # a pulse leaves the core and travels outward, ring by ring
        for pts in chains:
            paths.append(
                f'<path class="r" d="{smooth_path(densify(simplify(pts)))}" pathLength="1" '
                f'stroke="{colour}" stroke-width="{width:.2f}" stroke-opacity="{opacity:.2f}" '
                f'style="animation-delay:{draw:.2f}s,{ripple:.2f}s"/>'
            )
        if index:
            # read the ring's value off where it crosses a ray to the upper right
            target = -0.3
            best = min(
                (p for pts in chains for p in pts if 96 < p[1] < H - 96 and p[0] < W - 170),
                key=lambda p: abs(math.atan2(p[1] - CY, p[0] - CX) - target),
                default=None,
            )
            if best and abs(math.atan2(best[1] - CY, best[0] - CX) - target) <= 0.05:
                labels.append(
                    f'<text class="lbl" x="{best[0]:.1f}" y="{best[1] + 3.5:.1f}" '
                    f'style="animation-delay:{draw + 1.6:.2f}s">{kelvin * (k + 1) / n:.2f}</text>'
                )

    adv = 54
    line1, line2 = KOAN
    koan = (glyphs(line1, CX - (len(line1) - 1) * adv / 2, CY - 14, adv, "k", 1.3, 0.11)
            + glyphs(line2, CX - (len(line2) - 1) * adv / 2, CY + 48, adv, "k", 1.3 + len(line1) * 0.11 + 0.2, 0.11))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">{line1}，{line2}。</title>
<desc id="d">Isotherms around a quiet core. T = {kelvin:.2f} K, observed {observed}.</desc>
<style>
.r{{fill:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.8s cubic-bezier(.65,0,.25,1) forwards,ripple 6.5s ease-in-out infinite both}}
.lbl{{font:500 11px {MONO};fill:{c["muted"]};text-anchor:middle;paint-order:stroke;stroke:{c["bg"]};stroke-width:5px;opacity:0;animation:fade 1.2s ease forwards}}
.k{{font:400 40px {SERIF};fill:{c["ink"]};text-anchor:middle;animation:arrive 1.6s cubic-bezier(.2,.6,.2,1) both}}
.meta{{font:500 12.5px {MONO};fill:{c["muted"]};letter-spacing:.14em;opacity:0;animation:fade 1.4s ease 3s forwards}}
.inst{{stroke:{c["muted"]};stroke-width:1;fill:none;opacity:.55}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
@keyframes ripple{{0%,22%,100%{{opacity:.5}}9%{{opacity:1}}}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes arrive{{from{{opacity:0;filter:blur(9px);transform:translateY(10px)}}to{{opacity:1;filter:blur(0);transform:none}}}}
@media (prefers-reduced-motion:reduce){{.r{{animation:none;stroke-dashoffset:0}}.lbl,.k,.meta{{animation:none;opacity:1;filter:none}}}}
</style>
<defs>
<radialGradient id="v" cx="50%" cy="50%" r="62%"><stop offset=".55" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<mask id="m"><rect width="{W}" height="{H}" fill="url(#v)"/></mask>
<clipPath id="c"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#c)">
<rect width="{W}" height="{H}" fill="{c["bg"]}"/>
<g mask="url(#m)">{"".join(paths)}</g>
<g>{"".join(labels)}</g>
{frame(H)}
{koan}
<text class="meta" x="56" y="66">T = {kelvin:.2f} K</text>
<text class="meta" x="{W - 56}" y="66" text-anchor="end">dS ≥ δQ / T</text>
<text class="meta" x="56" y="{H - 56}">OBS · {observed}</text>
<text class="meta" x="{W - 56}" y="{H - 56}" text-anchor="end">Nº {plate_no}</text>
</g>
</svg>
"""


def thermal_svg(weeks, kelvin, observed):
    """The contribution calendar seen through an infrared camera."""
    h, pitch, size = 380, 18.6, 14.2
    x0, y0 = 92, 112
    days = [d for w in weeks for d in w]
    top = max(n for _, n in days) or 1
    flicker = random.Random(days[-1][0])
    cells, glow, starts = [], [], []
    where = {}
    for col, week in enumerate(weeks):
        delay = 0.6 + col * 0.032
        month = dt.date.fromisoformat(week[-1][0]).month
        if not starts or starts[-1][1] != month:
            starts.append((col, month))
        for date, n in week:
            row = (dt.date.fromisoformat(date).weekday() + 1) % 7  # Sunday first, as GitHub draws it
            x, y = x0 + col * pitch, y0 + row * pitch
            where[date] = (x + size / 2, y + size / 2)
            t = math.log1p(n) / math.log1p(top)
            colour = ramp(IRONBOW, t)
            cells.append(f'<rect class="c" x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="3" '
                         f'fill="{colour}" style="animation-delay:{delay:.2f}s"/>')
            if n:
                # the heat haze shows first, then the sweep brings the grid into focus; each warm cell shimmers on its own clock
                glow.append(f'<circle class="c f" cx="{x + size / 2:.1f}" cy="{y + size / 2:.1f}" r="{8 + 18 * t:.1f}" '
                            f'fill="{colour}" style="animation-delay:{flicker.uniform(0.1, 0.5):.2f}s,{flicker.uniform(1.5, 5):.2f}s;'
                            f'animation-duration:.9s,{flicker.uniform(2.2, 4.8):.2f}s"/>')
    months = "".join(
        f'<text class="mo" x="{x0 + col * pitch:.1f}" y="{y0 + 7 * pitch + 16:.1f}">'
        f'{dt.date(2000, month, 1).strftime("%b").upper()}</text>'
        for (col, month), nxt in zip(starts, starts[1:] + [(len(weeks) + 3, 0)])
        if nxt[0] - col >= 3
    )
    sweep_end = 0.6 + len(weeks) * 0.032
    grid_w, grid_h = len(weeks) * pitch, 7 * pitch - (pitch - size)

    def lock(date, label, cls, delay, above):
        """Corner brackets on a cell, with a leader out of the grid to its reading."""
        cx, cy = where[date]
        r, arm = 13, 5
        corners = "".join(
            f'M{cx + sx * r:.1f} {cy + sy * (r - arm):.1f}V{cy + sy * r:.1f}H{cx + sx * (r - arm):.1f}'
            for sx in (-1, 1) for sy in (-1, 1)
        )
        ly = y0 - 22 if above else y0 + grid_h + 40
        leader = f'M{cx:.1f} {cy + (-r if above else r):.1f}V{ly + (4 if above else -12):.1f}'
        anchor = "end" if cx > x0 + grid_w - 160 else "start"
        tx = cx + 6 if anchor == "start" else cx - 6
        return (f'<g class="{cls}" style="animation-delay:{delay:.2f}s">'
                f'<path d="{corners}{leader}"/><text x="{tx:.1f}" y="{ly:.1f}" text-anchor="{anchor}">{label}</text></g>')

    hot_date, hot_n = max(days, key=lambda d: d[1])
    today, today_n = days[-1]
    locks = lock(hot_date, f"MAX {hot_n} · {hot_date[5:]}", "lock hot", sweep_end + 0.2, True)
    if today != hot_date:
        locks += lock(today, f"SP1 {today_n} · NOW", "lock now", sweep_end + 0.7, False)

    sx = x0 + grid_w + 26
    scale = "".join(f'<stop offset="{k / (len(IRONBOW) - 1):.3f}" stop-color="{col}"/>' for k, col in enumerate(reversed(IRONBOW)))
    total = sum(n for _, n in days)
    vf = "".join(  # viewfinder corners
        f'<path d="M{x} {y + sy * 18}V{y}H{x + sx_ * 18}"/>'
        for x, y, sx_, sy in ((44, 44, 1, 1), (W - 44, 44, -1, 1), (44, h - 44, 1, -1), (W - 44, h - 44, -1, -1))
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-labelledby="t">
<title id="t">过去一年的贡献，透过红外相机观察。共 {total} 次，最热的一天是 {hot_date}（{hot_n}）。</title>
<style>
text{{font:500 13px {MONO};fill:#6b7380;letter-spacing:.12em}}
.c{{opacity:0;animation:fade .5s ease forwards}}
.f{{animation-name:fade,shimmer;animation-timing-function:ease,ease-in-out;animation-iteration-count:1,infinite;animation-direction:normal,alternate;animation-fill-mode:forwards,none}}
.mo{{font-size:11.5px;fill:#4f5661}}
.ui{{opacity:0;animation:fade 1s ease 2.6s forwards}}
.rec{{fill:#ff3b30;animation:blink 1.4s steps(1) infinite}}
.lock{{opacity:0;fill:none;stroke-width:1.4;animation:fade .4s ease forwards,pulse 2.4s ease-in-out infinite}}
.lock text{{stroke:none;font-size:12.5px}}
.lock path{{stroke-width:1.2}}
.hot{{stroke:#fdd25a}}.hot text{{fill:#fdd25a}}
.now{{stroke:#8ec5d6}}.now text{{fill:#8ec5d6}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:.15}}}}
@keyframes pulse{{50%{{stroke-opacity:.35}}}}
@keyframes shimmer{{from{{opacity:1}}to{{opacity:.55}}}}
@media (prefers-reduced-motion:reduce){{.c,.ui,.lock{{animation:none;opacity:1}}.rec{{animation:none}}.sweep,.scan{{display:none}}}}
</style>
<defs>
<filter id="bloom" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="11"/></filter>
<linearGradient id="scale" x1="0" y1="0" x2="0" y2="1">{scale}</linearGradient>
<linearGradient id="beam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".85" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity=".85"/></linearGradient>
<linearGradient id="band" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".045"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<pattern id="lines" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#fff" fill-opacity=".022"/></pattern>
<radialGradient id="vig" cx="50%" cy="50%" r="75%"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>
<clipPath id="clip"><rect width="{W}" height="{h}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#clip)">
<rect width="{W}" height="{h}" fill="#07080c"/>
<g filter="url(#bloom)">{"".join(glow)}</g>
<g>{"".join(cells)}</g>
{months}
<rect class="sweep" x="{x0 - 40}" y="{y0 - 14}" width="40" height="{grid_h + 28:.1f}" fill="url(#beam)" opacity="0">
<animate attributeName="x" from="{x0 - 40}" to="{x0 + grid_w - 20:.0f}" begin=".6s" dur="{sweep_end - 0.6:.2f}s" fill="freeze"/>
<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.05;.92;1" begin=".6s" dur="{sweep_end - 0.6:.2f}s" fill="freeze"/>
</rect>
{locks}
<rect width="{W}" height="{h}" fill="url(#lines)"/>
<rect class="scan" y="-60" width="{W}" height="60" fill="url(#band)"><animate attributeName="y" from="-60" to="{h}" dur="5.5s" repeatCount="indefinite"/></rect>
<rect width="{W}" height="{h}" fill="url(#vig)"/>
<g fill="none" stroke="#3a414c" stroke-width="1.2">{vf}</g>
<circle class="rec" cx="68" cy="66" r="4"/>
<text x="80" y="70" style="fill:#c9ccd1">REC</text>
<g class="ui">
<text x="128" y="70">IR · {len(weeks)}W × 7D</text>
<text x="{CX}" y="70" text-anchor="middle">ε 0.98 · λ 8–14 µm</text>
<text x="{W - 68}" y="70" text-anchor="end">{observed}</text>
<rect x="{sx:.1f}" y="{y0}" width="8" height="{grid_h:.1f}" rx="2" fill="url(#scale)"/>
<text x="{sx + 16:.1f}" y="{y0 + 8}" style="font-size:11.5px">{top}</text>
<text x="{sx + 16:.1f}" y="{y0 + grid_h:.1f}" style="font-size:11.5px">0</text>
<text x="68" y="{h - 60}">Σ {total:,} / 365 D</text>
<text x="{W - 68}" y="{h - 60}" text-anchor="end">T(7D) {kelvin:.2f} K</text>
</g>
</g>
</svg>
"""


def axioms_svg(theme):
    c = THEMES[theme]
    size, adv, lh, top = 21, 25, 38, 112
    h = top + (len(AXIOMS) - 1) * lh + 86
    widest = max(len(text) for _, text in AXIOMS) * adv
    left = CX - widest / 2 + 30  # first glyph's left edge; numbers hang in the margin
    lines, t = [], 0.5
    for k, (num, text) in enumerate(AXIOMS):
        y = top + k * lh
        lines.append(f'<text class="n" x="{left - 28:.1f}" y="{y}" style="animation-delay:{t:.2f}s">{num}</text>')
        if text:
            lines.append(glyphs(text, left + adv / 2, y, adv, "g", t + 0.15, 0.022))
            t += 0.15 + len(text) * 0.022 + 0.3
        else:  # 7 is left unsaid
            lines.append(f'<rect class="cur" x="{left:.1f}" y="{y - size + 3}" width="10" height="{size}" '
                         f'style="animation-delay:{t + 0.5:.2f}s"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-labelledby="t">
<title id="t">{"  ".join(f"{num} {text}" for num, text in AXIOMS if text)}  7</title>
<style>
.g{{font:400 {size}px {SERIF};fill:{c["ink"]};text-anchor:middle;animation:arrive .7s ease both}}
.n{{font:500 13px {MONO};fill:{c["muted"]};text-anchor:end;letter-spacing:.08em;animation:fade .6s ease both}}
.cur{{fill:{c["ice"]};opacity:0;animation:blink 1.1s steps(1) infinite}}
.meta{{font:500 12.5px {MONO};fill:{c["muted"]};letter-spacing:.14em}}
.inst{{stroke:{c["muted"]};stroke-width:1;fill:none;opacity:.55}}
@keyframes arrive{{from{{opacity:0;filter:blur(4px);transform:translateY(5px)}}to{{opacity:1;filter:blur(0);transform:none}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.g,.n{{animation:none}}.cur{{animation:none;opacity:1}}}}
</style>
<clipPath id="c"><rect width="{W}" height="{h}" rx="18"/></clipPath>
<g clip-path="url(#c)">
<rect width="{W}" height="{h}" fill="{c["bg"]}"/>
{frame(h)}
<text class="meta" x="56" y="66">PROPOSITIONS</text>
<text class="meta" x="{W - 56}" y="66" text-anchor="end">1 — 7</text>
{"".join(lines)}
</g>
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    weeks = fetch_days(LOGIN, token)
    days = [d for w in weeks for d in w]

    last7 = sum(n for _, n in days[-7:])
    kelvin = 2.725 + 0.18 * last7  # an idle week sits at the cosmic background
    heat = min(1.0, math.log1p(last7) / math.log1p(200))

    today = dt.date.fromisoformat(days[-1][0])
    year, week, _ = today.isocalendar()

    grid = field(Perlin(year * 100 + week), heat)
    rings = []
    level = 22.0
    while level < 520:
        chains = isolines(grid, level)
        if chains:
            rings.append((level, chains))
        level += RING_GAP

    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        svg = isotherm_svg(theme, rings, heat, kelvin, today.isoformat(), f"{year}·{week:02d}")
        (OUT / f"isotherm-{theme}.svg").write_text(svg, encoding="utf-8")
        (OUT / f"axioms-{theme}.svg").write_text(axioms_svg(theme), encoding="utf-8")
    (OUT / "thermal.svg").write_text(thermal_svg(weeks, kelvin, today.isoformat()), encoding="utf-8")
    print(f"T = {kelvin:.2f} K  heat = {heat:.2f}  rings = {len(rings)}  weeks = {len(weeks)}")


if __name__ == "__main__":
    main()
