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

# ColorBrewer RdBu, cold to hot, as used by Ed Hawkins' warming stripes.
RDBU = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7",
        "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"]

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

def isotherm_svg(theme, rings, heat, kelvin, observed, plate_no):
    c = THEMES[theme]
    n = len(rings)
    paths, labels = [], []
    for k, (level, chains) in enumerate(rings):
        u = k / max(n - 1, 1)
        colour = mix(c["ice"], c["ember"], u ** 1.4 * heat)
        index = k % 5 == 4
        width = (1.35 if index else 0.8) - 0.3 * u
        opacity = 0.92 - 0.5 * u
        delay = 0.25 + k * 0.07
        cls = "r b" if k < 3 else "r"
        for pts in chains:
            paths.append(
                f'<path class="{cls}" d="{smooth_path(densify(simplify(pts)))}" pathLength="1" '
                f'stroke="{colour}" stroke-width="{width:.2f}" stroke-opacity="{opacity:.2f}" '
                f'style="animation-delay:{delay:.2f}s"/>'
            )
        if index:
            # read the ring's value off where it crosses a ray to the upper right
            target = -0.3
            best = min(
                (p for pts in chains for p in pts if 96 < p[1] < H - 96 and p[0] < W - 170),
                key=lambda p: abs(math.atan2(p[1] - CY, p[0] - CX) - target),
                default=None,
            )
            if best and abs(math.atan2(best[1] - CY, best[0] - CX) - target) > 0.05:
                best = None
            if best:
                value = kelvin * (k + 1) / n
                labels.append(
                    f'<text class="lbl" x="{best[0]:.1f}" y="{best[1] + 3.5:.1f}" '
                    f'style="animation-delay:{delay + 1.6:.2f}s">{value:.2f}</text>'
                )

    ticks = []
    for x in range(40, W - 39, 20):
        long = (x - 40) % 100 == 0
        for y0, sign in ((22, 1), (H - 22, -1)):
            ticks.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + sign * (7 if long else 3.5)}"/>')
    crosses = []
    for x, y in ((40, 40), (W - 40, 40), (40, H - 40), (W - 40, H - 40)):
        crosses.append(f'<path d="M{x - 6} {y}h12M{x} {y - 6}v12"/>')

    line1, line2 = KOAN
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">{line1}，{line2}。</title>
<desc id="d">Isotherms around a quiet core. T = {kelvin:.2f} K, observed {observed}.</desc>
<style>
.r{{fill:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.8s cubic-bezier(.65,0,.25,1) forwards}}
.b{{animation:draw 2.8s cubic-bezier(.65,0,.25,1) forwards,breathe 7s ease-in-out 4s infinite alternate}}
.lbl{{font:500 10px {MONO};fill:{c["muted"]};text-anchor:middle;paint-order:stroke;stroke:{c["bg"]};stroke-width:5px;opacity:0;animation:fade 1.2s ease forwards}}
.koan{{font:400 40px {SERIF};fill:{c["ink"]};text-anchor:middle;letter-spacing:.32em;opacity:0;filter:blur(7px);animation:condense 2.6s cubic-bezier(.2,.6,.2,1) 1.1s forwards}}
.meta{{font:500 11px {MONO};fill:{c["muted"]};letter-spacing:.14em;opacity:0;animation:fade 1.4s ease 2.6s forwards}}
.inst{{stroke:{c["muted"]};stroke-width:1;fill:none;opacity:.55}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
@keyframes breathe{{from{{stroke-opacity:.9}}to{{stroke-opacity:.25}}}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes condense{{to{{opacity:1;filter:blur(0)}}}}
@media (prefers-reduced-motion:reduce){{.r,.b{{animation:none;stroke-dashoffset:0}}.lbl,.koan,.meta{{animation:none;opacity:1;filter:none}}}}
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
<g class="inst">{"".join(ticks)}{"".join(crosses)}</g>
<text class="koan" x="{CX}" y="{CY - 14}">{line1}</text>
<text class="koan" x="{CX}" y="{CY + 48}">{line2}</text>
<text class="meta" x="56" y="66">T = {kelvin:.2f} K</text>
<text class="meta" x="{W - 56}" y="66" text-anchor="end">dS ≥ δQ / T</text>
<text class="meta" x="56" y="{H - 56}">OBS · {observed}</text>
<text class="meta" x="{W - 56}" y="{H - 56}" text-anchor="end">Nº {plate_no}</text>
</g>
</svg>
"""


def stripes_svg(weekly):
    sw, sh = W / len(weekly), 84
    top = max(max(weekly), 60)
    colours = [ramp(RDBU, math.log1p(v) / math.log1p(top)) for v in weekly]
    bars, k = [], 0
    while k < len(colours):
        # merge equal neighbours so long silences do not show anti-aliasing seams
        run = 1
        while k + run < len(colours) and colours[k + run] == colours[k]:
            run += 1
        bars.append(
            f'<rect x="{k * sw:.2f}" width="{run * sw + 0.6:.2f}" height="{sh}" fill="{colours[k]}" '
            f'style="animation-delay:{k * 0.028:.3f}s"/>'
        )
        k += run
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {sh}" width="{W}" height="{sh}" role="img" aria-label="{len(weekly)} weeks, coldest blue to warmest red">
<style>
rect{{opacity:0;animation:in .9s ease forwards}}
@keyframes in{{to{{opacity:1}}}}
@media (prefers-reduced-motion:reduce){{rect{{animation:none;opacity:1}}}}
</style>
<clipPath id="c"><rect width="{W}" height="{sh}" rx="10" style="opacity:1;animation:none"/></clipPath>
<g clip-path="url(#c)">{"".join(bars)}</g>
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
    weekly = [sum(n for _, n in w) for w in weeks]
    (OUT / "stripes.svg").write_text(stripes_svg(weekly), encoding="utf-8")
    print(f"T = {kelvin:.2f} K  heat = {heat:.2f}  rings = {len(rings)}  weeks = {len(weekly)}")


if __name__ == "__main__":
    main()
