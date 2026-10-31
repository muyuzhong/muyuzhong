"""Render the profile as a Singularity-to-Prism Git spectrum, drawn from public contributions.

One spark of human creativity (the source / vector / first prompt) enters the AI prism
(the runtime / velocity / lever) and refracts into multi-language commit trajectories.

Usage: GITHUB_TOKEN=... python scripts/generate.py [login]
Only the standard library is used, so the workflow needs no install step.
"""

import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "muyuzhong"
OUT = Path(__file__).resolve().parent.parent / "assets"

TITLE = "AI is the velocity; creativity is the vector."
SUBTITLE = "AI is the runtime — the infinite lever of productivity. Creativity is the source — the origin of everything."
CLOSING = "Before the next token, creativity writes the first prompt."
COMMAND = "git log --graph --prism"

W, H = 1200, 620
SINGULARITY_X = 104    # the origin spark of creativity
PRISM_LEFT = 232       # where the single incident beam enters the AI prism
PRISM_CX = 266         # center axis of the crystalline AI prism
PRISM_RIGHT = 300      # where the refracted spectral rays exit the prism
TRACK_START = 356      # oldest week on the spectral timeline
TRACK_END = 988        # newest week (HEAD) on the spectral timeline
MAIN_Y = 424           # optical axis & main commit spine
LANE_GAP = 32          # vertical separation between refracted language beams
MAX_LANES = 6
SKIP_LANGS = {"CSS", "HTML"}

# GitHub's own surfaces + warm incandescent gold for Creativity + electric cyan for the AI Prism.
THEMES = {
    "dark": dict(
        bg="#0a0d12", surface="#0f141c", panel="#121822", border="#212834", rule="#1b222d",
        fg="#e6edf3", sub="#9198a1", muted="#656d76", rail="#484f58",
        gold="#f5b942", gold_bright="#fff5d6", gold_dim="#5c4314",
        cyan="#39c5cf", cyan_bright="#7ce8f0", cyan_dim="#133d45",
        hash="#d29922", branch="#3fb950",
        prism_fill="#122332", prism_edge="#39c5cf",
        lanes=["#ff7b72", "#58a6ff", "#d2a8ff", "#f0883e", "#3fb950", "#39c5cf"],
    ),
    "light": dict(
        bg="#fbfcfd", surface="#f3f5f8", panel="#eef1f5", border="#d0d7de", rule="#e2e7ed",
        fg="#1f2328", sub="#4d555e", muted="#656d76", rail="#8c959f",
        gold="#b56200", gold_bright="#8a4600", gold_dim="#f7e3c4",
        cyan="#086986", cyan_bright="#0550ae", cyan_dim="#cfeef5",
        hash="#9a6700", branch="#1a7f37",
        prism_fill="#e6f4f8", prism_edge="#086986",
        lanes=["#cf222e", "#0969da", "#8250df", "#bc4c00", "#1a7f37", "#086986"],
    ),
}

MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"
SERIF = "Georgia,'Times New Roman','Songti SC','Noto Serif SC',serif"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Noto Sans CJK SC',sans-serif"


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
# Fetching the top repository languages allows multi-language projects (e.g. Astro/Rust/JS) to refract into their own spectral lanes.
BY_REPO = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
  contributionsCollection(from:$from,to:$to){commitContributionsByRepository(maxRepositories:100){
    repository{primaryLanguage{name} languages(first:5,orderBy:{field:SIZE,direction:DESC}){totalSize edges{size node{name}}}}
    contributions(first:100){nodes{occurredAt commitCount}}}}}}"""


def fetch(token):
    cal = graphql(token, CALENDAR, {"login": LOGIN})["contributionCalendar"]["weeks"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in cal]
    start = dt.date.fromisoformat(weeks[0][0][0])
    end = dt.date.fromisoformat(weeks[-1][-1][0]) + dt.timedelta(days=1)
    by_language = {}
    cursor = start
    while cursor < end:
        upto = min(cursor + dt.timedelta(days=91), end)
        span = {"login": LOGIN, "from": f"{cursor}T00:00:00Z", "to": f"{upto}T00:00:00Z"}
        for entry in graphql(token, BY_REPO, span)["commitContributionsByRepository"]:
            repo = entry["repository"]
            langs = repo.get("languages") or {}
            total_size = langs.get("totalSize") or 0
            edges = langs.get("edges") or []
            weights = []
            for e in edges:
                name = e["node"]["name"]
                share = e["size"] / total_size if total_size else 0
                if name not in SKIP_LANGS and share >= 0.03:
                    weights.append((name, share))
            if not weights and repo.get("primaryLanguage"):
                primary = repo["primaryLanguage"]["name"]
                if primary:
                    weights.append((primary, 1.0))
            for node in entry["contributions"]["nodes"]:
                day = node["occurredAt"][:10]
                commits = node["commitCount"]
                for name, share in weights:
                    days = by_language.setdefault(name, {})
                    days[day] = days.get(day, 0) + max(1, round(commits * share))
        cursor = upto
    return weeks, by_language


def head_hash():
    sha = os.environ.get("GITHUB_SHA")
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                 cwd=OUT.parent).stdout.strip()
        except OSError:
            sha = ""
    return (sha or "0" * 7)[:7]


# ── layout ────────────────────────────────────────────────────────────

def build(weeks, by_language):
    """Weeks indexed k=0 (newest/HEAD) to k=span-1 (oldest), plus one spectral lane per language."""
    week_of = {date: k for k, w in enumerate(reversed(weeks)) for date, _ in w}
    totals = [sum(n for _, n in w) for w in reversed(weeks)]

    lanes = []
    for lang, days in by_language.items():
        counts = {}
        for day, n in days.items():
            if day in week_of:
                counts[week_of[day]] = counts.get(week_of[day], 0) + n
        if counts:
            lanes.append(dict(name=lang.lower(), counts=counts, total=sum(counts.values()),
                              newest=min(counts), oldest=max(counts)))
    lanes.sort(key=lambda lane: -lane["total"])
    lanes = lanes[:MAX_LANES]
    for i, lane in enumerate(lanes):
        lane["slot"] = (i // 2 + 1) * (-1 if i % 2 == 0 else 1)  # above, below, further above, …

    oldest = max((lane["oldest"] for lane in lanes), default=0)
    span = min(max(oldest + 4, 24), len(totals))
    return totals[:span], lanes


def week_x(k, span):
    """Map week k (k=span-1 is oldest near the prism, k=0 is newest/HEAD on the right)."""
    if span <= 1:
        return TRACK_END
    progress = (span - 1 - k) / (span - 1)
    return TRACK_START + progress * (TRACK_END - TRACK_START)


def radius(n, top):
    return 0 if n == 0 else 2.6 + 5.2 * math.sqrt(n / top)


def refraction_paths(lane, span):
    """Build (1) prism dispersion fan, (2) full carrier wave, and (3) active commit segment."""
    slot = lane["slot"]
    y = MAIN_Y + slot * LANE_GAP
    exit_y = MAIN_Y + slot * 11.5
    # Inside prism: from left entry (PRISM_LEFT, MAIN_Y) to right exit facet (PRISM_RIGHT, exit_y)
    # Outside prism: smooth cubic bezier into horizontal lane y at TRACK_START
    prism_fan = (
        f"M{PRISM_LEFT} {MAIN_Y}"
        f"L{PRISM_RIGHT} {exit_y:.1f}"
        f"C{PRISM_RIGHT + 22} {exit_y:.1f} {TRACK_START - 26} {y} {TRACK_START} {y}"
    )
    x_old = week_x(lane["oldest"], span)
    x_new = week_x(lane["newest"], span)
    carrier = f"M{TRACK_START} {y}H{TRACK_END}"
    motion_path = f"{prism_fan}H{x_new:.1f}"
    active_track = f"M{x_old:.1f} {y}H{x_new:.1f}"
    return prism_fan, carrier, motion_path, active_track, x_old, x_new, y


def packet(path_id, colour, dur, begin, r=2.8):
    """A photon/commit packet travelling forward along a path from Singularity/Prism toward HEAD."""
    timing = f'dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"'
    return (f'<circle r="{r}" fill="{colour}" opacity="0">'
            f'<animateMotion {timing} keyPoints="0;1" keyTimes="0;1" calcMode="linear"><mpath href="#{path_id}"/></animateMotion>'
            f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.08;.9;1" {timing}/></circle>')


# ── plate ─────────────────────────────────────────────────────────────

def render(theme, totals, lanes, sha, today):
    c = THEMES[theme]
    span = len(totals)
    total_commits = sum(totals)
    top = max(totals + [n for lane in lanes for n in lane["counts"].values()]) or 1
    date_str = f"{today:%b} {today.day}, {today.year}"

    # 1. Optical Paths: Singularity -> AI Prism -> Multi-language Git Spectrum
    incident_d = f"M{SINGULARITY_X} {MAIN_Y}H{PRISM_LEFT}"
    main_d = f"M{PRISM_LEFT} {MAIN_Y}H{TRACK_END}"

    carriers, branches, nodes, labels, packets = [], [], [], [], []

    # Incident golden photon from Singularity into Prism
    packets.append(packet("incident-ray", c["gold"], 1.8, 0.1, r=3.2))
    # Main spine photon from Prism to HEAD
    packets.append(packet("main-ray", c["cyan"], 6.5, 0.8, r=3.0))

    for i, lane in enumerate(lanes):
        colour = c["lanes"][i % len(c["lanes"])]
        prism_fan, carrier_d, motion_d, active_d, _, x_new, y = refraction_paths(lane, span)
        delay = 0.35 + i * 0.12

        # 1) Refracted ray exiting the AI Prism + hidden full motion path for photons
        carriers.append(
            f'<path id="l{i}" d="{motion_d}" fill="none" stroke="none"/>'
            f'<path d="{prism_fan}" fill="none" stroke="{colour}" stroke-width="1.9" stroke-opacity="0.78"/>'
            f'<path d="{carrier_d}" fill="none" stroke="{colour}" stroke-width="1.2" '
            f'stroke-dasharray="2 5" stroke-opacity="0.30"/>'
        )
        # 2) Solid active commit trajectory between oldest and newest commit weeks
        branches.append(
            f'<path class="br" d="{active_d}" pathLength="1" stroke="{colour}" '
            f'style="animation-delay:{delay:.2f}s"/>'
        )
        # Weekly commit nodes along the language beam
        for k, n in sorted(lane["counts"].items(), reverse=True):
            wx = week_x(k, span)
            r = radius(n, top)
            node_delay = delay + 0.35 + (span - 1 - k) * 0.02
            branches.append(
                f'<circle class="pop" cx="{wx:.1f}" cy="{y}" r="{r:.1f}" fill="{colour}" '
                f'style="animation-delay:{node_delay:.2f}s"/>'
            )
        # Active frontier pulse ring on recent branches
        if lane["newest"] <= 2:
            branches.append(
                f'<circle class="tip" cx="{x_new:.1f}" cy="{y}" r="8.5" stroke="{colour}" '
                f'style="animation-delay:{delay + 0.9:.2f}s"/>'
            )
        # Right-hand aligned spectrum legend (ample 140px column width, zero overlap)
        labels.append(
            f'<g class="fade" style="animation-delay:{delay + 0.55:.2f}s">'
            f'<circle cx="{TRACK_END + 30}" cy="{y}" r="3.5" fill="{colour}"/>'
            f'<text class="lb-name" x="{TRACK_END + 42}" y="{y + 4}" fill="{colour}">{lane["name"]}</text>'
            f'<text class="lb-val" x="{W - 44}" y="{y + 4}">{lane["total"]}</text>'
            f'</g>'
        )
        packets.append(packet(f"l{i}", colour, 5.2 + i * 0.7, 1.0 + i * 0.65, r=2.5))

    # Main commit spine nodes (weekly totals across all repos)
    for k, n in enumerate(totals):
        wx = week_x(k, span)
        r = radius(n, top)
        node_delay = 0.3 + (span - 1 - k) * 0.02
        if r:
            paint = f'r="{r:.1f}" fill="{c["fg"]}"'
        else:
            paint = f'r="2.2" fill="{c["bg"]}" stroke="{c["rail"]}" stroke-width="1.2"'
        nodes.append(
            f'<circle class="pop" cx="{wx:.1f}" cy="{MAIN_Y}" {paint} '
            f'style="animation-delay:{node_delay:.2f}s"/>'
        )

    # HEAD frontier badge at (TRACK_END, MAIN_Y)
    labels.append(
        f'<g class="fade" style="animation-delay:0.5s">'
        f'<circle cx="{TRACK_END + 30}" cy="{MAIN_Y}" r="4" fill="{c["cyan"]}"/>'
        f'<text class="lb-name" x="{TRACK_END + 42}" y="{MAIN_Y + 4}" fill="{c["cyan"]}" font-weight="700">HEAD</text>'
        f'<text class="lb-val-hi" x="{W - 44}" y="{MAIN_Y + 4}">{total_commits:,}</text>'
        f'</g>'
    )

    # Chronological month labels (reading naturally Left -> Right)
    spans = {}
    for k in range(span):
        m_name = (today - dt.timedelta(weeks=k)).strftime("%b")
        spans.setdefault(m_name, []).append(week_x(k, span))
    months = [
        f'<text class="mo" x="{sum(xs) / len(xs):.1f}" y="{MAIN_Y + 132}">{name}</text>'
        for name, xs in spans.items() if len(xs) >= 2
    ]

    # Crystalline Prism geometry centered at (PRISM_CX, MAIN_Y)
    prism_top = MAIN_Y - 96
    prism_bot = MAIN_Y + 96
    prism_outer = f"{PRISM_CX},{prism_top} {PRISM_RIGHT + 10},{MAIN_Y} {PRISM_CX},{prism_bot} {PRISM_LEFT - 10},{MAIN_Y}"
    prism_inner = f"{PRISM_CX},{prism_top + 18} {PRISM_RIGHT},{MAIN_Y} {PRISM_CX},{prism_bot - 18} {PRISM_LEFT},{MAIN_Y}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" aria-labelledby="t d">
<title id="t">{TITLE}</title>
<desc id="d">{SUBTITLE} {CLOSING} Live GitHub contribution spectrum across {span} weeks and {total_commits:,} contributions.</desc>
<style>
.mono{{font-family:{MONO}}}
.serif{{font-family:{SERIF}}}
.sans{{font-family:{SANS}}}
.ps{{font-family:{MONO};font-size:14px;fill:{c["branch"]};font-weight:600}}
.cmd{{font-family:{MONO};font-size:14px;fill:{c["fg"]}}}
.seal{{font-family:{SANS};font-size:13px;fill:{c["sub"]};letter-spacing:1.5px;text-anchor:middle}}
.meta{{font-family:{MONO};font-size:13px;fill:{c["muted"]};text-anchor:end}}
.eyebrow-ai{{font-family:{MONO};font-size:12.5px;font-weight:700;fill:{c["cyan"]};letter-spacing:1.4px}}
.eyebrow-cr{{font-family:{MONO};font-size:12.5px;font-weight:700;fill:{c["gold"]};letter-spacing:1.4px}}
.h1-ai{{font-family:{MONO};font-size:40px;font-weight:700;fill:{c["fg"]};letter-spacing:-0.8px}}
.h1-cr{{font-family:{SERIF};font-size:46px;font-style:italic;font-weight:400;fill:url(#gold-grad)}}
.sub-line{{font-family:{SANS};font-size:15.5px;fill:{c["sub"]}}}
.axiom{{font-family:{MONO};font-size:13px;fill:{c["muted"]}}}
.ribbon-txt{{font-family:{MONO};font-size:12.5px;fill:{c["sub"]}}}
.stage-title{{font-family:{MONO};font-size:13px;font-weight:700;letter-spacing:1.2px;text-anchor:middle}}
.stage-sub{{font-family:{SERIF};font-size:14px;font-style:italic;fill:{c["sub"]};text-anchor:middle}}
.stage-code{{font-family:{MONO};font-size:12px;fill:{c["muted"]};text-anchor:middle}}
.leg-hd-l{{font-family:{MONO};font-size:11.5px;font-weight:600;fill:{c["muted"]};letter-spacing:0.8px;text-anchor:start}}
.leg-hd-r{{font-family:{MONO};font-size:11.5px;font-weight:600;fill:{c["muted"]};letter-spacing:0.8px;text-anchor:end}}
.lb-name{{font-family:{MONO};font-size:13px;text-anchor:start}}
.lb-val{{font-family:{MONO};font-size:12.5px;fill:{c["muted"]};text-anchor:end}}
.lb-val-hi{{font-family:{MONO};font-size:12.5px;fill:{c["fg"]};font-weight:600;text-anchor:end}}
.mo{{font-family:{MONO};font-size:12px;fill:{c["muted"]};text-anchor:middle;text-transform:uppercase;letter-spacing:1px}}
.ft{{font-family:{MONO};font-size:13.5px;fill:{c["muted"]}}}
.br{{fill:none;stroke-width:2.4;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:0;animation:draw 1.4s cubic-bezier(.5,0,.2,1) both}}
.main-rail{{fill:none;stroke:{c["rail"]};stroke-width:2;stroke-dasharray:1;stroke-dashoffset:0;animation:draw 1.2s ease-out both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.3,1.5,.5,1) both}}
.fade{{animation:fade .6s ease both}}
.ring-gold{{fill:none;stroke:{c["gold"]};transform-box:fill-box;transform-origin:center;animation:pulse 3.2s ease-out infinite}}
.ring-cyan{{fill:none;stroke:{c["cyan"]};transform-box:fill-box;transform-origin:center;animation:pulse 2.8s ease-out infinite}}
.tip{{fill:none;stroke-width:1.4;transform-box:fill-box;transform-origin:center;animation:pulse 2.8s ease-out infinite}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes draw{{from{{stroke-dashoffset:1}}to{{stroke-dashoffset:0}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@keyframes pulse{{0%{{opacity:.85;transform:scale(.65)}}100%{{opacity:0;transform:scale(2.3)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.ring-gold,.ring-cyan,.tip{{display:none}}}}
</style>

<defs>
  <linearGradient id="gold-grad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{c["gold_bright"]}"/>
    <stop offset="55%" stop-color="{c["gold"]}"/>
    <stop offset="100%" stop-color="{c["fg"]}"/>
  </linearGradient>
  <linearGradient id="incident-grad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="{c["gold_bright"]}"/>
    <stop offset="65%" stop-color="{c["gold"]}"/>
    <stop offset="100%" stop-color="{c["cyan"]}"/>
  </linearGradient>
  <linearGradient id="prism-grad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{c["cyan"]}" stop-opacity="0.28"/>
    <stop offset="50%" stop-color="{c["prism_fill"]}" stop-opacity="0.75"/>
    <stop offset="100%" stop-color="{c["gold"]}" stop-opacity="0.20"/>
  </linearGradient>
  <radialGradient id="glow-singularity" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="{c["gold"]}" stop-opacity="0.22"/>
    <stop offset="100%" stop-color="{c["gold"]}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glow-prism" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="{c["cyan"]}" stop-opacity="0.20"/>
    <stop offset="100%" stop-color="{c["cyan"]}" stop-opacity="0"/>
  </radialGradient>
</defs>

<!-- Background Plate & Border -->
<rect width="{W}" height="{H}" rx="14" fill="{c["bg"]}"/>
<rect x="0.75" y="0.75" width="{W - 1.5}" height="{H - 1.5}" rx="13.25" fill="none" stroke="{c["border"]}" stroke-width="1.5"/>

<!-- Ambient Optical Glows -->
<circle cx="{SINGULARITY_X}" cy="{MAIN_Y}" r="120" fill="url(#glow-singularity)"/>
<circle cx="{PRISM_CX}" cy="{MAIN_Y}" r="155" fill="url(#glow-prism)"/>

<!-- 1. Top Telemetry Bar -->
<text class="ps" x="44" y="36">~/{LOGIN}</text>
<text class="cmd" x="{44 + (len(LOGIN) + 3) * 8.6:.1f}" y="36">❯ {COMMAND}</text>
<text class="seal" x="{W / 2:.0f}" y="36"><tspan fill="{c["gold"]}">「</tspan> AI 即生产力 · 创造力即一切 <tspan fill="{c["gold"]}">」</tspan></text>
<text class="meta" x="{W - 44}" y="36"><tspan fill="{c["hash"]}">commit {sha}</tspan> (<tspan fill="{c["cyan"]}" font-weight="700">HEAD</tspan> → <tspan fill="{c["branch"]}" font-weight="700">main</tspan>) · {date_str}</text>
<line x1="44" y1="54" x2="{W - 44}" y2="54" stroke="{c["rule"]}" stroke-width="1"/>

<!-- 2. Dual-Axis Philosophical Manifesto -->
<!-- Left Column: 01 // AI IS THE VELOCITY (Monospace / Runtime / Productivity) -->
<g id="manifesto-ai">
  <rect x="44" y="68" width="528" height="156" rx="10" fill="{c["surface"]}" stroke="{c["border"]}" stroke-width="1"/>
  <rect x="64" y="88" width="8" height="8" rx="1.5" fill="{c["cyan"]}"/>
  <text class="eyebrow-ai" x="80" y="96">01 // THE RUNTIME · INFINITE EXECUTION</text>
  <text class="h1-ai" x="64" y="142">AI IS THE VELOCITY<tspan fill="{c["cyan"]}">.</tspan></text>
  <text class="sub-line" x="64" y="174">AI is the <tspan fill="{c["fg"]}" font-weight="600">runtime</tspan> &amp; <tspan fill="{c["cyan"]}" font-weight="600">lever</tspan> — turning intent into throughput.</text>
  <text class="axiom" x="64" y="202"><tspan fill="{c["cyan"]}">▸</tspan> Predicts the next token · scales productivity to infinity.</text>
</g>

<!-- Center Coupling Node (Velocity × Vector) -->
<g id="manifesto-coupling">
  <line x1="{W / 2:.0f}" y1="86" x2="{W / 2:.0f}" y2="206" stroke="{c["border"]}" stroke-width="1" stroke-dasharray="3 4"/>
  <circle cx="{W / 2:.0f}" cy="146" r="14" fill="{c["panel"]}" stroke="{c["border"]}" stroke-width="1.2"/>
  <text class="mono" x="{W / 2:.0f}" y="151" font-size="15" fill="{c["sub"]}" text-anchor="middle">×</text>
</g>

<!-- Right Column: 02 // Creativity is the vector (Editorial Serif Italic / Source / Everything) -->
<g id="manifesto-creativity">
  <rect x="628" y="68" width="528" height="156" rx="10" fill="{c["surface"]}" stroke="{c["border"]}" stroke-width="1"/>
  <polygon points="652,86 654,90 658,92 654,94 652,98 650,94 646,92 650,90" fill="{c["gold"]}"/>
  <text class="eyebrow-cr" x="666" y="96">02 // THE SOURCE · SOVEREIGN GENESIS</text>
  <text class="h1-cr" x="648" y="144">Creativity is the vector.</text>
  <text class="sub-line" x="648" y="174">Creativity is the <tspan fill="{c["gold"]}" font-weight="600">source</tspan> — the direction &amp; meaning of <tspan fill="{c["fg"]}" font-weight="600">everything</tspan>.</text>
  <text class="axiom" x="648" y="202"><tspan fill="{c["gold"]}">✦</tspan> Writes the first prompt · defines what deserves to exist.</text>
</g>

<!-- 3. Telemetry Bridge Bar -->
<rect x="44" y="238" width="{W - 88}" height="30" rx="6" fill="{c["panel"]}" stroke="{c["rule"]}" stroke-width="1"/>
<circle cx="62" cy="253" r="4" fill="{c["gold"]}"/>
<text class="ribbon-txt" x="74" y="257"><tspan fill="{c["gold"]}" font-weight="600">SOURCE(1)</tspan> : THE FIRST PROMPT</text>
<text class="ribbon-txt" x="{W / 2 - 20:.0f}" y="257" text-anchor="middle" fill="{c["cyan"]}">───► [ AI PRISM : RUNTIME REFRACTION ] ───►</text>
<text class="ribbon-txt" x="{W - 60}" y="257" text-anchor="end">PROOF : <tspan fill="{c["branch"]}" font-weight="700">{total_commits:,} CONTRIBUTIONS(+)</tspan> · {len(lanes)} LANGUAGES</text>

<!-- 4. Singularity -> AI Prism -> Git Spectrum Stage -->
<!-- Subtle horizontal optical axis -->
<line x1="44" y1="{MAIN_Y}" x2="{TRACK_END}" y2="{MAIN_Y}" stroke="{c["rule"]}" stroke-width="1" stroke-dasharray="2 6"/>

<!-- Stage I: THE SINGULARITY (Creativity / The Spark) -->
<g id="singularity">
  <text class="stage-title" x="{SINGULARITY_X}" y="338" fill="{c["gold"]}">THE SPARK</text>
  <text class="stage-sub" x="{SINGULARITY_X}" y="356">creativity</text>
  <circle cx="{SINGULARITY_X}" cy="{MAIN_Y}" r="36" fill="none" stroke="{c["gold"]}" stroke-width="1" stroke-dasharray="2 5" stroke-opacity="0.5"/>
  <circle class="ring-gold" cx="{SINGULARITY_X}" cy="{MAIN_Y}" r="15" stroke-width="1.6"/>
  <circle class="ring-gold" cx="{SINGULARITY_X}" cy="{MAIN_Y}" r="22" stroke-width="1.2" style="animation-delay:1.4s"/>
  <line x1="{SINGULARITY_X - 22}" y1="{MAIN_Y}" x2="{SINGULARITY_X + 22}" y2="{MAIN_Y}" stroke="{c["gold"]}" stroke-width="1.2" stroke-opacity="0.7"/>
  <line x1="{SINGULARITY_X}" y1="{MAIN_Y - 22}" x2="{SINGULARITY_X}" y2="{MAIN_Y + 22}" stroke="{c["gold"]}" stroke-width="1.2" stroke-opacity="0.7"/>
  <circle cx="{SINGULARITY_X}" cy="{MAIN_Y}" r="7" fill="{c["gold_bright"]}" stroke="{c["gold"]}" stroke-width="2.5"/>
  <text class="stage-code" x="{SINGULARITY_X}" y="{MAIN_Y + 58}">1st prompt</text>
  <text class="stage-code" x="{SINGULARITY_X}" y="{MAIN_Y + 75}" fill="{c["gold"]}">vector(1)</text>
</g>

<!-- Incident Laser Beam (Intent -> Compute) -->
<line x1="{SINGULARITY_X + 7}" y1="{MAIN_Y}" x2="{PRISM_LEFT}" y2="{MAIN_Y}" stroke="{c["gold"]}" stroke-width="6" stroke-opacity="0.18"/>
<path id="incident-ray" d="{incident_d}" fill="none" stroke="url(#incident-grad)" stroke-width="2.6"/>

<!-- Stage II: THE AI PRISM (Runtime Amplifier) -->
<g id="ai-prism">
  <text class="stage-title" x="{PRISM_CX}" y="308" fill="{c["cyan"]}">AI PRISM</text>
  <text class="stage-code" x="{PRISM_CX}" y="324">runtime × velocity</text>
  <!-- Outer and inner crystalline diamond facets -->
  <polygon points="{prism_outer}" fill="url(#prism-grad)" stroke="{c["prism_edge"]}" stroke-width="1.8"/>
  <polygon points="{prism_inner}" fill="none" stroke="{c["cyan"]}" stroke-width="1" stroke-opacity="0.45" stroke-dasharray="3 3"/>
  <line x1="{PRISM_CX}" y1="{prism_top}" x2="{PRISM_CX}" y2="{prism_bot}" stroke="{c["cyan"]}" stroke-width="1" stroke-opacity="0.35"/>
  <circle class="ring-cyan" cx="{PRISM_LEFT}" cy="{MAIN_Y}" r="7" stroke-width="1.4"/>
  <circle cx="{PRISM_LEFT}" cy="{MAIN_Y}" r="3.5" fill="{c["gold_bright"]}" stroke="{c["cyan"]}" stroke-width="1.5"/>
  <text class="stage-code" x="{PRISM_CX}" y="{prism_bot + 22}" fill="{c["cyan"]}">scales execution</text>
</g>

<!-- Stage III: Refracted Multi-Language Git Spectrum -->
<path id="main-ray" class="main-rail" d="{main_d}" pathLength="1"/>
{"".join(carriers)}
{"".join(branches)}
{"".join(nodes)}
{"".join(packets)}

<!-- Frontier Divider & Right-Hand Spectrum Legend -->
<line x1="{TRACK_END + 14}" y1="308" x2="{TRACK_END + 14}" y2="536" stroke="{c["rule"]}" stroke-width="1" stroke-dasharray="2 4"/>
<text class="leg-hd-l" x="{TRACK_END + 26}" y="302">SPECTRUM</text>
<text class="leg-hd-r" x="{W - 44}" y="302">COMMITS</text>
{"".join(labels)}

<!-- Chronological Month Axis -->
{"".join(months)}

<!-- 5. Footer Bar -->
<line x1="44" y1="572" x2="{W - 44}" y2="572" stroke="{c["rule"]}" stroke-width="1"/>
<text class="ft" x="44" y="598">{span} weeks observed · <tspan fill="{c["branch"]}" font-weight="600">{total_commits:,} contributions(+)</tspan> · <tspan fill="{c["gold"]}">1 spark</tspan> → <tspan fill="{c["cyan"]}">∞ throughput</tspan></text>
<text class="ft" x="{W - 44}" y="598" text-anchor="end" fill="{c["sub"]}">{CLOSING}</text>
</svg>
"""


def main():
    cache_file = os.environ.get("GITHUB_CACHE_JSON")
    if cache_file and Path(cache_file).exists():
        data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
        weeks, by_language = data["weeks"], data["by_language"]
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        weeks, by_language = fetch(token)

    totals, lanes = build(weeks, by_language)
    today = dt.date.fromisoformat(weeks[-1][-1][0])
    sha = head_hash()

    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for theme in THEMES:
        (OUT / f"log-{theme}.svg").write_text(render(theme, totals, lanes, sha, today), encoding="utf-8")
    print(f"{len(totals)} weeks, lanes: " + ", ".join(f"{l['name']}({l['total']}, slot {l['slot']})" for l in lanes))


if __name__ == "__main__":
    main()
