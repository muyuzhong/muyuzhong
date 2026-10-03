"""Render the profile as one `git log --graph`, drawn from public contributions.

The sentence is the HEAD commit's message, each language is a branch lane,
and every node is a week of real commits.

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

MESSAGE = "每一次提交，都是对昨天的一次温柔否定。"
COMMAND = "git log --graph"

W, H = 1200, 580
RAIL_X = 72            # the graph column the HEAD commit sits on
MAIN_Y = 408           # where the rail turns into history
HEAD_X = 124           # this week's node, just past the turn
LANE_GAP = 40
MAX_LANES = 6

# GitHub's own surfaces, so the image melts into the page; lane colours are git's terminal palette.
THEMES = {
    "dark": dict(bg="#0d1117", fg="#e6edf3", muted="#7d8590", rail="#484f58",
                 hash="#d29922", head="#39c5cf", branch="#3fb950",
                 lanes=["#ff7b72", "#58a6ff", "#bc8cff", "#d29922", "#3fb950", "#39c5cf"]),
    "light": dict(bg="#ffffff", fg="#1f2328", muted="#656d76", rail="#afb8c1",
                  hash="#9a6700", head="#1b7c83", branch="#1a7f37",
                  lanes=["#cf222e", "#0969da", "#8250df", "#9a6700", "#1a7f37", "#1b7c83"]),
}

MONO = "ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"
SANS = "'PingFang SC','Noto Sans SC','Noto Sans CJK SC','Source Han Sans SC','Microsoft YaHei',sans-serif"


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
    repository{primaryLanguage{name}} contributions(first:100){nodes{occurredAt commitCount}}}}}}"""


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
            lang = (entry["repository"]["primaryLanguage"] or {}).get("name")
            if not lang:
                continue
            days = by_language.setdefault(lang, {})
            for node in entry["contributions"]["nodes"]:
                day = node["occurredAt"][:10]
                days[day] = days.get(day, 0) + node["commitCount"]
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
    """Weeks newest first, as git log reads, plus one lane per language."""
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

    # show back to a little before the oldest branch, so the active stretch fills the width
    oldest = max((lane["oldest"] for lane in lanes), default=0)
    span = min(max(oldest + 4, 20), len(totals))
    return totals[:span], lanes


def week_x(k, span):
    return HEAD_X + k * (W - 60 - HEAD_X) / (span - 1)


def radius(n, top):
    return 0 if n == 0 else 2.6 + 5.4 * math.sqrt(n / top)


def lane_path(lane, span):
    """Fork off main past the oldest commit, merge back before the newest; an active branch stays open."""
    y = MAIN_Y + lane["slot"] * LANE_GAP
    xa, xb = week_x(lane["newest"], span), week_x(lane["oldest"], span)
    bend = 26
    fork = f"L{xb + 6:.1f} {y}C{xb + bend * .6:.1f} {y} {xb + bend * .4:.1f} {MAIN_Y} {xb + bend:.1f} {MAIN_Y}"
    if lane["newest"] <= 1:
        return f"M{xa - 4:.1f} {y}" + fork, True
    merge = f"M{xa - bend:.1f} {MAIN_Y}C{xa - bend * .4:.1f} {MAIN_Y} {xa - bend * .6:.1f} {y} {xa - 6:.1f} {y}"
    return merge + fork, False


def glyphs(text, x, y, advance, cls, start, step):
    """One <text> per glyph on a fixed grid, so each can arrive on its own whatever the fallback font."""
    return "".join(
        f'<text class="{cls}" x="{x + i * advance:.1f}" y="{y}" style="animation-delay:{start + i * step:.2f}s">'
        f'{ch.replace("&", "&amp;").replace("<", "&lt;")}</text>'
        for i, ch in enumerate(text)
    )


def packet(path_id, colour, dur, begin, r=2.6):
    """A commit travelling along a path from its far end towards HEAD, forever."""
    timing = f'dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"'
    return (f'<circle r="{r}" fill="{colour}" opacity="0">'
            f'<animateMotion {timing} keyPoints="1;0" keyTimes="0;1" calcMode="linear"><mpath href="#{path_id}"/></animateMotion>'
            f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.1;.88;1" {timing}/></circle>')


# ── plate ─────────────────────────────────────────────────────────────

def render(theme, totals, lanes, sha, today):
    c = THEMES[theme]
    span = len(totals)
    top = max(totals + [n for lane in lanes for n in lane["counts"].values()]) or 1

    # terminal header: the prompt types itself, then git log prints the HEAD commit
    ch = 9.8
    prompt_end = 0.35 + (len(COMMAND) + 2) * 0.045
    prompt = (f'<text class="ps" x="60" y="56">~/{LOGIN}</text>'
              + glyphs("❯ " + COMMAND, 60 + (len(LOGIN) + 3) * ch + ch / 2, 56, ch, "ty", 0.35, 0.045))
    out = prompt_end + 0.25
    date = f"{today:%a %b} {today.day} {today.year}"
    header = (
        f'<text class="ln" x="100" y="117" style="animation-delay:{out:.2f}s">'
        f'<tspan fill="{c["hash"]}">commit {sha} (</tspan>'
        f'<tspan fill="{c["head"]}" font-weight="700">HEAD</tspan><tspan fill="{c["hash"]}"> → </tspan>'
        f'<tspan fill="{c["branch"]}" font-weight="700">main</tspan><tspan fill="{c["hash"]}">)</tspan></text>'
        f'<text class="ln" x="100" y="148" style="animation-delay:{out + .1:.2f}s">Author: {LOGIN}</text>'
        f'<text class="ln" x="100" y="176" xml:space="preserve" style="animation-delay:{out + .2:.2f}s">Date:   {date}</text>'
    )
    msg_start = out + 0.55
    adv, msg_x = 42, 132
    message = glyphs(MESSAGE, msg_x + adv / 2, 258, adv, "msg", msg_start, 0.07)
    cursor = (f'<rect class="cur" x="{msg_x + len(MESSAGE) * adv + 6}" y="226" width="4" height="40" '
              f'style="animation-delay:{msg_start + len(MESSAGE) * 0.07 + 0.1:.2f}s"/>')

    # history: the rail drops from HEAD and turns into the main line, newest week first
    draw = out + 0.3
    main = f"M{RAIL_X} 124V{MAIN_Y - 24}Q{RAIL_X} {MAIN_Y} {RAIL_X + 24} {MAIN_Y}H{W - 20}"
    nodes = []
    for k, n in enumerate(totals):
        x, delay, r = week_x(k, span), draw + 0.9 + k * 0.035, radius(n, top)
        paint = f'r="{r:.1f}" fill="{c["fg"]}"' if r else f'r="2.2" fill="{c["bg"]}" stroke="{c["rail"]}" stroke-width="1.2"'
        nodes.append(f'<circle class="pop" cx="{x:.1f}" cy="{MAIN_Y}" {paint} style="animation-delay:{delay:.2f}s"/>')

    branches, labels, packets = [], [], []
    lanes_at = draw + 1.6
    for i, lane in enumerate(lanes):
        colour = c["lanes"][i % len(c["lanes"])]
        y = MAIN_Y + lane["slot"] * LANE_GAP
        d, active = lane_path(lane, span)
        delay = lanes_at + i * 0.25
        branches.append(f'<path id="l{i}" class="br" d="{d}" pathLength="1" stroke="{colour}" '
                        f'style="animation-delay:{delay:.2f}s"/>')
        for k, n in sorted(lane["counts"].items()):
            branches.append(f'<circle class="pop" cx="{week_x(k, span):.1f}" cy="{y}" r="{radius(n, top):.1f}" '
                            f'fill="{colour}" style="animation-delay:{delay + 0.5 + (k - lane["newest"]) * 0.03:.2f}s"/>')
        if active:  # an open branch keeps its tip ring breathing
            branches.append(f'<circle class="tip" cx="{week_x(lane["newest"], span):.1f}" cy="{y}" r="9" '
                            f'stroke="{colour}" style="animation-delay:{delay + 1:.2f}s"/>')
        labels.append(f'<text class="lb" x="{week_x(lane["oldest"], span) + 34:.1f}" y="{y + 4}" fill="{colour}" '
                      f'style="animation-delay:{delay + 0.7:.2f}s">{lane["name"]}</text>')
        length = week_x(lane["oldest"], span) - week_x(lane["newest"], span) + 60
        packets.append(packet(f"l{i}", colour, length / 90, lanes_at + 1.6 + i * 1.3))
    packets.append(packet("main", c["head"], 9, lanes_at + 1, r=3))

    spans = {}  # each month's label sits over the middle of its weeks
    for k in range(span):
        spans.setdefault((today - dt.timedelta(weeks=k)).strftime("%b"), []).append(week_x(k, span))
    months = [f'<text class="mo" x="{sum(xs) / len(xs):.1f}" y="{MAIN_Y + 112}">{name}</text>'
              for name, xs in spans.items() if len(xs) >= 2]
    tail = draw + 3.2

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t">
<title id="t">{MESSAGE}</title>
<style>
text{{font-family:{MONO}}}
.ps{{font-size:16px;fill:{c["branch"]}}}
.ty{{font-size:16px;fill:{c["fg"]};text-anchor:middle;opacity:0;animation:fade .01s linear forwards}}
.ln{{font-size:16px;fill:{c["muted"]};opacity:0;animation:fade .35s ease forwards}}
.msg{{font:500 38px {SANS};fill:{c["fg"]};text-anchor:middle;animation:arrive .8s cubic-bezier(.2,.7,.2,1) both}}
.cur{{fill:{c["head"]};opacity:0;animation:blink 1.06s steps(1) infinite}}
.rail{{fill:none;stroke:url(#fadeout);stroke-width:2;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.8s cubic-bezier(.6,0,.2,1) {draw:.2f}s forwards}}
.br{{fill:none;stroke-width:2;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1s cubic-bezier(.6,0,.2,1) forwards}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.3,1.6,.5,1) both}}
.head{{fill:{c["bg"]};stroke:{c["head"]};stroke-width:2.4;opacity:0;animation:fade .3s ease {out:.2f}s forwards}}
.ring{{fill:none;stroke:{c["head"]};transform-box:fill-box;transform-origin:center;opacity:0;animation:ring 2.8s ease-out {tail:.2f}s infinite}}
.tip{{fill:none;stroke-width:1.4;transform-box:fill-box;transform-origin:center;opacity:0;animation:ring 2.8s ease-out infinite}}
.lb{{font-size:14px;opacity:0;animation:fade .5s ease forwards}}
.mo{{font-size:13px;fill:{c["muted"]};text-anchor:middle;text-transform:uppercase;opacity:0;animation:fade .6s ease {tail:.2f}s forwards}}
.ft{{font-size:15px;fill:{c["muted"]};opacity:0;animation:fade .6s ease {tail + .2:.2f}s forwards}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes arrive{{from{{opacity:0;filter:blur(6px);transform:translateY(8px)}}to{{opacity:1;filter:blur(0);transform:none}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
@keyframes pop{{from{{transform:scale(0)}}to{{transform:scale(1)}}}}
@keyframes ring{{0%{{opacity:.9;transform:scale(.6)}}100%{{opacity:0;transform:scale(2.4)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.ty,.ln,.head,.lb,.mo,.ft,.cur{{opacity:1}}.rail,.br{{stroke-dashoffset:0}}.ring,.tip{{display:none}}}}
</style>
<defs>
<linearGradient id="fadeout" gradientUnits="userSpaceOnUse" x1="{W - 260}" y1="0" x2="{W - 20}" y2="0">
<stop offset="0" stop-color="{c["rail"]}"/><stop offset="1" stop-color="{c["rail"]}" stop-opacity="0"/></linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="{c["bg"]}"/>
{prompt}
<path id="main" class="rail" d="{main}" pathLength="1"/>
<circle class="ring" cx="{RAIL_X}" cy="112" r="7"/>
<circle class="head" cx="{RAIL_X}" cy="112" r="7"/>
{header}
{message}{cursor}
{"".join(branches)}
{"".join(nodes)}
{"".join(packets)}
{"".join(labels)}
{"".join(months)}
<text class="ft" x="60" y="{H - 22}">{span} weeks changed, <tspan fill="{c["branch"]}">{sum(totals):,} contributions(+)</tspan></text>
<text class="ft" x="{W - 60}" y="{H - 22}" text-anchor="end">{" · ".join(lane["name"] for lane in lanes)}</text>
</svg>
"""


def main():
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
