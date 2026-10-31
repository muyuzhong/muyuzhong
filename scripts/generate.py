"""Render the profile as an animated ASCII-terminal banner plus live contribution stats.

Outputs (assets/): hero.svg  — typed, glowing ASCII intro
                   stats.svg — character heatmap, streaks and language bars from real GitHub data

Usage: GITHUB_TOKEN=... python scripts/generate.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "muyuzhong"
NAME = "cheathero"
OUT = Path(__file__).resolve().parent.parent / "assets"
SKIP_LANGS = {"CSS", "HTML", "Shell", "Dockerfile"}


# ── data ──────────────────────────────────────────────────────────────

def graphql(token, query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": LOGIN},
    )
    for attempt in range(3):  # the API occasionally drops a handshake; a retry is enough
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]["contributionsCollection"]


CALENDAR = """query($login:String!){user(login:$login){contributionsCollection{
  contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""

# One window per quarter keeps every repository under 100 active days, so no nested paging is needed.
BY_REPO = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
  contributionsCollection(from:$from,to:$to){commitContributionsByRepository(maxRepositories:100){
    repository{primaryLanguage{name} languages(first:5,orderBy:{field:SIZE,direction:DESC}){totalSize edges{size node{name}}}}
    contributions(first:100){nodes{occurredAt commitCount}}}}}}"""


def fetch(token):
    cal = graphql(token, CALENDAR, {"login": LOGIN})["contributionCalendar"]["weeks"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in cal]
    start = dt.date.fromisoformat(weeks[0][0][0])
    end = dt.date.fromisoformat(weeks[-1][-1][0]) + dt.timedelta(days=1)
    languages = {}
    cursor = start
    while cursor < end:
        upto = min(cursor + dt.timedelta(days=91), end)
        span = {"login": LOGIN, "from": f"{cursor}T00:00:00Z", "to": f"{upto}T00:00:00Z"}
        for entry in graphql(token, BY_REPO, span)["commitContributionsByRepository"]:
            repo = entry["repository"]
            langs = repo.get("languages") or {}
            total_size = langs.get("totalSize") or 0
            weights = [(e["node"]["name"], e["size"] / total_size) for e in langs.get("edges") or []
                       if total_size and e["node"]["name"] not in SKIP_LANGS and e["size"] / total_size >= 0.03]
            if not weights and (repo.get("primaryLanguage") or {}).get("name"):
                weights.append((repo["primaryLanguage"]["name"], 1.0))
            commits = sum(n["commitCount"] for n in entry["contributions"]["nodes"])
            for name, share in weights:
                languages[name] = languages.get(name, 0) + max(1, round(commits * share))
        cursor = upto
    return weeks, languages


# ── stats ─────────────────────────────────────────────────────────────

def streaks(days):
    """days: chronological list of counts. Returns (longest, current); an empty today does not break the current streak."""
    longest = run = 0
    for n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    tail = days[:-1] if days and days[-1] == 0 else days
    current = 0
    for n in reversed(tail):
        if not n:
            break
        current += 1
    return longest, current


def levels(counts):
    nonzero = sorted(n for n in counts if n)
    if not nonzero:
        return lambda n: 0
    q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)]
    return lambda n: 0 if n == 0 else 1 + sum(n > t for t in q)


# ── ASCII terminal chrome ─────────────────────────────────────────────

BG, FG, DIM, FAINT = "#0a0c0a", "#e8ece8", "#7d867d", "#2b322b"
ACCENT = "#4ade80"  # the single accent colour
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono','Noto Sans Mono CJK SC',monospace"
CW = 8.4            # advance of one 14px monospace cell; textLength pins rows to it regardless of the viewer's font
W = 1200
COLS = 139          # characters in one full-width border row

NAME_FONT = {  # 5x5 block letters
    "C": ["█████", "█    ", "█    ", "█    ", "█████"],
    "H": ["█   █", "█   █", "█████", "█   █", "█   █"],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def border(title, right, h):
    """Box-drawing frame: title/status sit in the top rule, vertical rules are drawn per row."""
    left = f"┌─[ {title} ]"
    status = f"[ {right} ]─┐"
    fill = "─" * (COLS - len(left) - len(status))
    pulse_status = esc(status).replace("●", f'<tspan class="pulse" fill="{ACCENT}">●</tspan>')
    top = (f'<text class="m" x="14" y="22" textLength="{COLS * CW:.0f}" fill="{FAINT}">'
           f'{esc(left[:3])}<tspan fill="{ACCENT}">{esc(left[3:])}</tspan>{fill}'
           f'<tspan fill="{DIM}">{pulse_status}</tspan></text>')
    bottom = f'<text class="m" x="14" y="{h - 12}" textLength="{COLS * CW:.0f}" fill="{FAINT}">└{"─" * (COLS - 2)}┘</text>'
    sides = "".join(
        f'<text class="m" x="14" y="{y}" fill="{FAINT}">│</text><text class="m" x="{14 + (COLS - 1) * CW:.1f}" y="{y}" fill="{FAINT}">│</text>'
        for y in range(44, h - 20, 20))
    return top + bottom + sides


def typed(text, x, y, start, fill, step=0.03, size=15, extra=""):
    """One <text> whose characters appear one by one. Returns (svg, end_time)."""
    chars = "".join(f'<tspan class="t" style="animation-delay:{start + i * step:.2f}s">{esc(ch)}</tspan>'
                    for i, ch in enumerate(text))
    return (f'<text class="m" xml:space="preserve" x="{x}" y="{y}" font-size="{size}" fill="{fill}">{chars}{extra}</text>',
            start + len(text) * step)


BASE_CSS = f"""
text{{font-family:{MONO}}}
.m{{white-space:pre}}
.t{{animation:appear .01s both}}
@keyframes appear{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
.rise{{animation:rise .6s cubic-bezier(.2,.8,.2,1) both}}
.pulse{{animation:blink 1.6s steps(1) infinite}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""


def svg(h, title, desc, css, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" font-size="14" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">{title}</title>
<desc id="d">{desc}</desc>
<style>{BASE_CSS}{css}</style>
<rect width="{W}" height="{h}" rx="14" fill="{BG}"/>
{body}
</svg>
"""


# ── hero ──────────────────────────────────────────────────────────────

def render_hero():
    H = 340
    fs, cw, lh = 22, 13.2, 25
    word = NAME.upper()
    rows = []
    for r in range(5):
        line = " ".join(NAME_FONT[ch][r] for ch in word)
        rows.append(f'<text class="m rise" xml:space="preserve" x="48" y="{112 + r * lh}" font-size="{fs}" textLength="{len(line) * cw:.0f}" '
                    f'fill="{ACCENT}" style="animation-delay:{0.15 + r * 0.12:.2f}s">{line}</text>')

    # signal field: a static character ramp whose brightness ripples across the grid
    ramp = "·:-=+*#%@"
    x0, y0, cols, nrows, lh2 = 800, 70, 44, 14, 18
    field = []
    for r in range(nrows):
        for k in range(cols):
            v = (math.sin(k * 0.34 + r * 0.55) + math.sin(k * 0.11 - r * 0.3) + 2) / 4
            ch = ramp[min(int(v * len(ramp)), len(ramp) - 1)]
            field.append(f'<text class="m f p{(k * 3 + r) % 16}" x="{x0 + k * CW:.1f}" y="{y0 + r * lh2}" '
                         f'fill="{ACCENT}" fill-opacity="{0.25 + 0.75 * v:.2f}">{ch}</text>')

    line_a, end_a = typed('$ echo "AI is the velocity; creativity is the vector."', 48, 266, 1.0, FG)
    line_a = line_a.replace('<tspan class="t" style="animation-delay:1.00s">$', f'<tspan class="t" fill="{ACCENT}" style="animation-delay:1.00s">$', 1)
    line_b, end_b = typed("> AI 即生产力，创造力即一切", 48, 292, end_a + 0.2, DIM, 0.06,
                          extra=f'<tspan class="cur" style="animation-delay:{end_a + 0.2 + 15 * 0.06:.2f}s" fill="{ACCENT}"> █</tspan>')
    chips = "  ".join(f'[{n}]' for n in ("TypeScript", "Python", "Rust", "Swift", "Astro"))
    chips_svg = (f'<text class="m rise" x="48" y="318" font-size="13" fill="{DIM}" style="animation-delay:.9s">{chips}</text>')

    css = """
.f{animation:shimmer 3.2s ease-in-out infinite}
@keyframes shimmer{0%,100%{opacity:.3}50%{opacity:1}}
""" + "".join(f".p{i}{{animation-delay:-{i * 0.2:.1f}s}}" for i in range(16)) + f"""
.cur{{animation:appear .01s both,blink 1.1s steps(1) infinite}}
.scan{{animation:scan 7s linear infinite}}
@keyframes scan{{from{{transform:translateY(0)}}to{{transform:translateY({H}px)}}}}
"""
    body = (f'<defs><clipPath id="c"><rect width="{W}" height="{H}" rx="14"/></clipPath></defs>'
            f'<g clip-path="url(#c)"><rect class="scan" y="-4" width="{W}" height="3" fill="{ACCENT}" opacity=".10"/></g>'
            + border(f"{NAME}@github", "● online", H)
            + "".join(rows) + "".join(field)
            + f'<text class="m" x="{x0}" y="{y0 - 14}" font-size="12" fill="{DIM}">// signal</text>'
            + line_a + line_b + chips_svg)
    return svg(H, f"{NAME} — AI is the velocity; creativity is the vector.",
               f"ASCII terminal banner for {NAME}: AI is the velocity, creativity is the vector.", css, body)


# ── stats ─────────────────────────────────────────────────────────────

def streaks(days):
    """days: chronological list of counts. Returns (longest, current); an empty today does not break the current streak."""
    longest = run = 0
    for n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    tail = days[:-1] if days and days[-1] == 0 else days
    current = 0
    for n in reversed(tail):
        if not n:
            break
        current += 1
    return longest, current


def levels(counts):
    nonzero = sorted(n for n in counts if n)
    if not nonzero:
        return lambda n: 0
    q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)]
    return lambda n: 0 if n == 0 else 1 + sum(n > t for t in q)


def render_stats(weeks, languages, today):
    flat = [n for w in weeks for _, n in w]
    total, active = sum(flat), sum(1 for n in flat if n)
    longest, current = streaks(flat)
    level = levels(flat)

    tiles = [("CONTRIBUTIONS", f"{total:,}", "past year"), ("ACTIVE DAYS", f"{active}", f"/ {len(flat)}"),
             ("LONGEST STREAK", f"{longest}", "days"), ("CURRENT STREAK", f"{current}", "days")]
    tile_svg = []
    for i, (label, value, unit) in enumerate(tiles):
        x = 48 + i * 280
        if i:
            tile_svg.append(f'<text class="m" x="{x - 24}" y="96" fill="{FAINT}">│</text><text class="m" x="{x - 24}" y="116" fill="{FAINT}">│</text><text class="m" x="{x - 24}" y="136" fill="{FAINT}">│</text>')
        tile_svg.append(
            f'<g class="rise" style="animation-delay:{i * 0.1:.1f}s">'
            f'<text class="m" x="{x}" y="86" font-size="12" fill="{DIM}">{label}</text>'
            f'<text class="m" x="{x}" y="128" font-size="38" font-weight="700" fill="{ACCENT}">{value}</text>'
            f'<text class="m" x="{x + len(value) * 23 + 10}" y="128" font-size="13" fill="{DIM}">{unit}</text></g>')

    x0, y0, pitch = 76, 196, 20
    glyph = ["·", "░░", "▒▒", "▓▓", "██"]
    opacity = [1, 0.35, 0.55, 0.78, 1]
    cells, months, last = [], [], -9
    for col, week in enumerate(weeks):
        d0 = dt.date.fromisoformat(week[0][0])
        if (col == 0 or d0.month != dt.date.fromisoformat(weeks[col - 1][0][0]).month) and col - last >= 3:
            months.append(f'<text class="m" x="{x0 + col * pitch - 8}" y="{y0 - 14}" font-size="12" fill="{DIM}">{d0:%b}</text>')
            last = col
        for date, n in week:
            dow = (dt.date.fromisoformat(date).weekday() + 1) % 7
            lv = level(n)
            fill = FAINT if lv == 0 else ACCENT
            cells.append(f'<text class="m c" x="{x0 + col * pitch}" y="{y0 + dow * pitch + 14}" font-size="14" text-anchor="middle" '
                         f'fill="{fill}" fill-opacity="{opacity[lv]}" style="animation-delay:{col * 0.012:.3f}s,{-(col * 0.11 + dow * 0.07):.2f}s">'
                         f'{glyph[lv]}<title>{date}: {n}</title></text>')
    days = "".join(f'<text class="m" x="48" y="{y0 + r * pitch + 14}" font-size="12" fill="{DIM}">{n}</text>'
                   for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri")))
    ly = y0 + 7 * pitch + 22
    legend = (f'<text class="m" x="{W - 48}" y="{ly}" font-size="12" text-anchor="end" fill="{DIM}">less '
              + "".join(f'<tspan fill="{FAINT if i == 0 else ACCENT}" fill-opacity="{opacity[i]}" font-size="14">{glyph[i]}</tspan>' for i in range(5))
              + " more</text>")

    all_total = sum(languages.values()) or 1
    langs = [kv for kv in sorted(languages.items(), key=lambda kv: -kv[1])[:6] if kv[1] / all_total >= 0.01]
    lang_total = sum(n for _, n in langs) or 1
    by = ly + 46
    BAR = 56
    rows = [f'<text class="m" x="48" y="{by - 14}" font-size="12" fill="{DIM}">// languages</text>']
    for i, (name, n) in enumerate(langs):
        share = n / lang_total
        filled = max(1, round(BAR * share))
        y = by + 14 + i * 26
        bar = "".join(f'<tspan class="t" fill="{ACCENT}" style="animation-delay:{0.5 + i * 0.12 + k * 0.012:.2f}s">█</tspan>' for k in range(filled))
        rows.append(f'<text class="m" x="48" y="{y}" font-size="15" fill="{FG}">{esc(name.lower())}</text>'
                    f'<text class="m" x="190" y="{y}" font-size="15" textLength="{BAR * 9:.0f}" fill="{FAINT}">{"░" * BAR}</text>'
                    f'<text class="m" x="190" y="{y}" font-size="15" textLength="{filled * 9}" lengthAdjust="spacing" xml:space="preserve">{bar}</text>'
                    f'<text class="m" x="{190 + BAR * 9 + 20}" y="{y}" font-size="15" fill="{DIM}">{share * 100:5.1f}%</text>')
    H = by + 14 + len(langs) * 26 + 34

    css = f"""
.c{{animation:appear .3s ease both,wave 3.2s ease-in-out infinite}}
@keyframes wave{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-6px)}}}}
"""
    footer = f'<text class="m" x="48" y="{H - 30}" font-size="13" fill="{DIM}">&gt; updated {today:%Y-%m-%d} · before the next token, creativity writes the first prompt.</text>'
    body = (border("activity", f"live · {today:%Y-%m-%d}", H) + "".join(tile_svg) + "".join(months) + days
            + "".join(cells) + legend + "".join(rows) + footer)
    return svg(H, f"{NAME}'s GitHub activity",
               f"{total:,} contributions across {active} active days; longest streak {longest} days.", css, body)


# ── main ──────────────────────────────────────────────────────────────

def main():
    cache_file = os.environ.get("GITHUB_CACHE_JSON")
    if cache_file and Path(cache_file).exists():
        data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
        weeks, languages = data["weeks"], data["languages"]
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        weeks, languages = fetch(token)
        if cache_file:
            Path(cache_file).write_text(json.dumps({"weeks": weeks, "languages": languages}), encoding="utf-8")

    today = dt.date.fromisoformat(weeks[-1][-1][0])
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    (OUT / "hero.svg").write_text(render_hero(), encoding="utf-8")
    (OUT / "stats.svg").write_text(render_stats(weeks, languages, today), encoding="utf-8")
    print("languages:", ", ".join(f"{k}({v})" for k, v in sorted(languages.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
