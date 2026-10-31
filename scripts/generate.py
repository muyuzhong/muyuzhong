"""Render the profile banner and live contribution stats as theme-aware SVGs.

Outputs (assets/): hero-{dark,light}.svg  — animated intro banner
                   stats-{dark,light}.svg — heatmap, streaks and language mix from real GitHub data

Usage: GITHUB_TOKEN=... python scripts/generate.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "muyuzhong"
NAME = "cheathero"
OUT = Path(__file__).resolve().parent.parent / "assets"
SKIP_LANGS = {"CSS", "HTML", "Shell", "Dockerfile"}

THEMES = {
    "dark": dict(
        bg="#0d1117", card="#151b23", border="#2a313c", fg="#f0f6fc", sub="#9da7b3", muted="#6e7681",
        a1="#8b7cf6", a2="#2dd4bf", a3="#f472b6", blob=0.30, dots="#30363d",
        heat=["#1b212b", "#35307f", "#5146d1", "#7c6ff2", "#b8aeff"],
    ),
    "light": dict(
        bg="#ffffff", card="#f6f8fa", border="#d8dee4", fg="#1f2328", sub="#59636e", muted="#818b98",
        a1="#6d4aff", a2="#0d9488", a3="#db2777", blob=0.22, dots="#d0d7de",
        heat=["#eceef2", "#d3ccfb", "#a99af5", "#7b5cf0", "#4f2fd0"],
    ),
}

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Inter','PingFang SC','Noto Sans CJK SC','Microsoft YaHei',sans-serif"
MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5", "Rust": "#dea584",
    "Swift": "#f05138", "Astro": "#ff5a03", "Go": "#00add8", "Java": "#b07219", "C": "#8a8a8a",
    "C++": "#f34b7d", "Kotlin": "#a97bff", "Vue": "#41b883", "Svelte": "#ff3e00", "Ruby": "#cc342d",
}
FALLBACK = ["#8b7cf6", "#2dd4bf", "#f472b6", "#fbbf24", "#60a5fa", "#fb923c"]


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


# ── shared chrome ─────────────────────────────────────────────────────

def frame(c, w, h, body, css, title, desc):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">{title}</title>
<desc id="d">{desc}</desc>
<style>
text{{font-family:{SANS}}}
.m{{font-family:{MONO}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
{body}
</svg>
"""


# ── hero ──────────────────────────────────────────────────────────────

def render_hero(theme):
    c = THEMES[theme]
    W, H = 1200, 320
    chips = ["TypeScript", "Python", "Rust", "Swift", "Astro"]
    chip_svg, x = [], 64
    for i, name in enumerate(chips):
        w = len(name) * 7.6 + 26
        chip_svg.append(
            f'<g class="rise" style="animation-delay:{0.7 + i * 0.07:.2f}s">'
            f'<rect x="{x:.1f}" y="236" width="{w:.1f}" height="30" rx="15" fill="{c["card"]}" stroke="{c["border"]}"/>'
            f'<circle cx="{x + 14:.1f}" cy="251" r="3.5" fill="{LANG_COLORS.get(name, c["a1"])}"/>'
            f'<text x="{x + 24:.1f}" y="256" font-size="13" font-weight="500" fill="{c["sub"]}">{name}</text></g>')
        x += w + 10

    code = [  # (indent, [(text, colour)])
        (0, [("const ", c["a3"]), (NAME, c["fg"]), (" = {", c["muted"])]),
        (1, [("lever", c["a2"]), (": ", c["muted"]), ('"AI"', c["a1"]), (",", c["muted"])]),
        (1, [("vector", c["a2"]), (": ", c["muted"]), ('"creativity"', c["a1"]), (",", c["muted"])]),
        (1, [("ships", c["a2"]), (": ", c["muted"]), ('["boardcast", "rea"]', c["a1"]), (",", c["muted"])]),
        (1, [("shipping", c["a2"]), (": ", c["muted"]), ("true", c["a3"]), (",", c["muted"])]),
        (0, [("};", c["muted"])]),
    ]
    lines = []
    for i, (indent, parts) in enumerate(code):
        spans = "".join(f'<tspan fill="{col}">{t.replace("&", "&amp;")}</tspan>' for t, col in parts)
        lines.append(f'<text class="m rise" xml:space="preserve" x="{752 + indent * 22}" y="{128 + i * 30}" font-size="17" '
                     f'style="animation-delay:{0.5 + i * 0.18:.2f}s">{spans}</text>')

    css = f"""
.rise{{animation:rise .7s cubic-bezier(.2,.8,.2,1) both}}
.b1{{animation:d1 14s ease-in-out infinite alternate}}
.b2{{animation:d2 17s ease-in-out infinite alternate}}
.b3{{animation:d3 19s ease-in-out infinite alternate}}
@keyframes d1{{to{{transform:translate(90px,40px)}}}}
@keyframes d2{{to{{transform:translate(-110px,-30px)}}}}
@keyframes d3{{to{{transform:translate(-60px,50px)}}}}
.dot{{animation:ping 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}}
@keyframes ping{{0%{{opacity:.7;transform:scale(1)}}100%{{opacity:0;transform:scale(3)}}}}
.cur{{animation:blink 1.1s steps(1) infinite}}
@keyframes blink{{50%{{opacity:0}}}}
"""
    body = f"""<defs>
  <clipPath id="clip"><rect width="{W}" height="{H}" rx="22"/></clipPath>
  <radialGradient id="g1"><stop offset="0" stop-color="{c["a1"]}" stop-opacity="{c["blob"]}"/><stop offset="1" stop-color="{c["a1"]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="g2"><stop offset="0" stop-color="{c["a2"]}" stop-opacity="{c["blob"]}"/><stop offset="1" stop-color="{c["a2"]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="g3"><stop offset="0" stop-color="{c["a3"]}" stop-opacity="{c["blob"] * 0.8:.2f}"/><stop offset="1" stop-color="{c["a3"]}" stop-opacity="0"/></radialGradient>
  <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="{c["dots"]}"/></pattern>
</defs>
<g clip-path="url(#clip)">
  <rect width="{W}" height="{H}" fill="{c["bg"]}"/>
  <rect width="{W}" height="{H}" fill="url(#dots)" opacity=".7"/>
  <circle class="b1" cx="250" cy="90" r="300" fill="url(#g1)"/>
  <circle class="b2" cx="1000" cy="260" r="320" fill="url(#g2)"/>
  <circle class="b3" cx="620" cy="360" r="260" fill="url(#g3)"/>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="21.5" fill="none" stroke="{c["border"]}"/>

<g class="rise">
  <rect x="64" y="46" width="132" height="28" rx="14" fill="{c["card"]}" stroke="{c["border"]}"/>
  <circle cx="82" cy="60" r="4" fill="{c["a2"]}"/><circle class="dot" cx="82" cy="60" r="4" fill="{c["a2"]}"/>
  <text x="94" y="65" font-size="12" font-weight="600" letter-spacing="1.4" fill="{c["sub"]}">HELLO, WORLD</text>
</g>
<text class="rise" x="60" y="152" font-size="86" font-weight="800" letter-spacing="-2.5" fill="{c["fg"]}" style="animation-delay:.1s">{NAME}<tspan fill="{c["a1"]}">.</tspan></text>
<text class="rise" x="64" y="192" font-size="23" fill="{c["sub"]}" style="animation-delay:.25s">AI is the <tspan font-weight="700" fill="{c["fg"]}">velocity</tspan>. Creativity is the <tspan font-weight="700" fill="{c["fg"]}">vector</tspan>.</text>
<text class="rise" x="64" y="218" font-size="15" fill="{c["muted"]}" style="animation-delay:.35s">AI 即生产力，创造力即一切</text>
{"".join(chip_svg)}

<g class="rise" style="animation-delay:.3s">
  <rect x="720" y="40" width="416" height="240" rx="14" fill="{c["card"]}" stroke="{c["border"]}"/>
  <circle cx="744" cy="62" r="5.5" fill="#ff5f57"/><circle cx="764" cy="62" r="5.5" fill="#febc2e"/><circle cx="784" cy="62" r="5.5" fill="#28c840"/>
  <text class="m" x="928" y="66" font-size="12" text-anchor="middle" fill="{c["muted"]}">me.ts</text>
  <line x1="721" y1="82" x2="1135" y2="82" stroke="{c["border"]}"/>
</g>
{"".join(lines)}
<rect class="cur" x="{752 + 2 * 11:.0f}" y="{128 + 5 * 30 - 15}" width="9" height="19" fill="{c["a1"]}" transform="translate(0 0)"/>"""
    return frame(c, W, H, body, css, f"{NAME} — AI is the velocity; creativity is the vector.",
                 f"{NAME}'s profile banner: AI is the velocity, creativity is the vector.")


# ── stats ─────────────────────────────────────────────────────────────

def render_stats(theme, weeks, languages, today):
    c = THEMES[theme]
    W = 1200
    flat = [n for w in weeks for _, n in w]
    total = sum(flat)
    active = sum(1 for n in flat if n)
    longest, current = streaks(flat)
    level = levels(flat)

    tiles = [("Contributions", f"{total:,}", "last 12 months", c["a1"]),
             ("Active days", f"{active}", f"of {len(flat)} days", c["a2"]),
             ("Longest streak", f"{longest}", "days in a row", c["a3"]),
             ("Current streak", f"{current}", "days", c["a1"])]
    tw, gap = 268, 16
    tile_svg = []
    for i, (label, value, note, col) in enumerate(tiles):
        x = 40 + i * (tw + gap)
        tile_svg.append(
            f'<g class="rise" style="animation-delay:{i * 0.08:.2f}s">'
            f'<rect x="{x}" y="72" width="{tw}" height="96" rx="14" fill="{c["card"]}" stroke="{c["border"]}"/>'
            f'<rect x="{x + 20}" y="86" width="22" height="4" rx="2" fill="{col}"/>'
            f'<text x="{x + 20}" y="124" font-size="34" font-weight="800" fill="{c["fg"]}">{value}</text>'
            f'<text x="{x + 20 + 14 + len(value) * 20:.0f}" y="124" font-size="13" fill="{c["muted"]}">{note}</text>'
            f'<text x="{x + 20}" y="152" font-size="13" font-weight="600" fill="{c["sub"]}">{label}</text></g>')

    # heatmap
    x0, y0, pitch, cell = 74, 224, 20, 16
    cells, months, last_col = [], [], -9
    for col, week in enumerate(weeks):
        d0 = dt.date.fromisoformat(week[0][0])
        if (col == 0 or d0.month != dt.date.fromisoformat(weeks[col - 1][0][0]).month) and col - last_col >= 3:
            months.append(f'<text x="{x0 + col * pitch}" y="{y0 - 12}" font-size="12" fill="{c["muted"]}">{d0:%b}</text>')
            last_col = col
        for row, (date, n) in enumerate(week):
            dow = (dt.date.fromisoformat(date).weekday() + 1) % 7  # Sunday-first like GitHub
            lv = level(n)
            cells.append(f'<rect class="c" x="{x0 + col * pitch}" y="{y0 + dow * pitch}" width="{cell}" height="{cell}" '
                         f'rx="4" fill="{c["heat"][lv]}" style="animation-delay:{col * 0.014:.3f}s"><title>{date}: {n}</title></rect>')
    days = "".join(f'<text x="40" y="{y0 + r * pitch + 12}" font-size="11" fill="{c["muted"]}">{n}</text>'
                   for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri")))
    ly = y0 + 7 * pitch + 6
    legend = "".join(f'<rect x="{1040 + i * 20}" y="{ly}" width="14" height="14" rx="4" fill="{col}"/>'
                     for i, col in enumerate(c["heat"]))
    legend += (f'<text x="{1040 - 8}" y="{ly + 11}" font-size="12" text-anchor="end" fill="{c["muted"]}">Less</text>'
               f'<text x="{1040 + 5 * 20 + 6}" y="{ly + 11}" font-size="12" fill="{c["muted"]}">More</text>')

    # language mix
    all_total = sum(languages.values()) or 1
    langs = [kv for kv in sorted(languages.items(), key=lambda kv: -kv[1])[:6] if kv[1] / all_total >= 0.01]
    lang_total = sum(n for _, n in langs) or 1
    by = ly + 54
    bar_w, bx, seg = W - 80, 40, []
    leg, cursor = [], 0.0
    step = (W - 80) / max(len(langs), 1)
    for i, (name, n) in enumerate(langs):
        col = LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])
        share = n / lang_total
        w = bar_w * share
        seg.append(f'<rect x="{bx + cursor:.1f}" y="{by}" width="{max(w - 3, 2):.1f}" height="12" fill="{col}"/>')
        cursor += w
        lx = 40 + i * step
        leg.append(f'<circle cx="{lx + 5:.0f}" cy="{by + 40}" r="5" fill="{col}"/>'
                   f'<text x="{lx + 18:.0f}" y="{by + 45}" font-size="14" font-weight="600" fill="{c["fg"]}">{name}'
                   f'<tspan dx="7" font-weight="400" fill="{c["muted"]}">{share * 100:.1f}%</tspan></text>')
    H = by + 76

    css = f"""
.rise{{animation:rise .6s cubic-bezier(.2,.8,.2,1) both}}
.c{{animation:fade .5s ease both}}
.bar{{animation:grow 1.2s cubic-bezier(.2,.8,.2,1) .4s both;transform-origin:{bx}px 0}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
"""
    body = f"""<defs><clipPath id="bar"><rect x="{bx}" y="{by}" width="{bar_w}" height="12" rx="6"/></clipPath></defs>
<rect width="{W}" height="{H}" rx="22" fill="{c["bg"]}"/>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="21.5" fill="none" stroke="{c["border"]}"/>
<text x="40" y="46" font-size="13" font-weight="700" letter-spacing="1.6" fill="{c["sub"]}">ACTIVITY</text>
<text x="{W - 40}" y="46" font-size="12" text-anchor="end" fill="{c["muted"]}">updated {today:%Y-%m-%d} · live from GitHub</text>
{"".join(tile_svg)}
{"".join(months)}{days}
{"".join(cells)}
{legend}
<text x="40" y="{by - 16}" font-size="13" font-weight="700" letter-spacing="1.6" fill="{c["sub"]}">LANGUAGES</text>
<rect x="{bx}" y="{by}" width="{bar_w}" height="12" rx="6" fill="{c["card"]}"/>
<g clip-path="url(#bar)"><g class="bar">{"".join(seg)}</g></g>
{"".join(leg)}"""
    return frame(c, W, H, body, css, f"{NAME}'s GitHub activity",
                 f"{total:,} contributions across {active} active days; longest streak {longest} days.")


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
    for theme in THEMES:
        (OUT / f"hero-{theme}.svg").write_text(render_hero(theme), encoding="utf-8")
        (OUT / f"stats-{theme}.svg").write_text(render_stats(theme, weeks, languages, today), encoding="utf-8")
    print("languages:", ", ".join(f"{k}({v})" for k, v in sorted(languages.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
