"""The last 12 months of GitHub contributions, as a platformer level.

Every week is a column whose height grows with log2 of that week's
contributions. A small pixel character with a VR headset runs the level from
left to right, hops for the coins above the five best weeks, and stops at a
flag on the current week. Rebuilt nightly by .github/workflows/contrib-level.yml.

    python3 scripts/contrib_level.py

Data comes from the GraphQL API when GITHUB_TOKEN is set, otherwise from the
public contribution calendar on the profile page.
"""
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_assets as B  # noqa: E402  (THEMES, frame, svg, text, n, discrete)

USER = os.environ.get("GH_USER", "ugursirvermez")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def fetch_graphql(user, token):
    query = """query($login: String!) { user(login: $login) { contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "contrib-level"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {d["date"]: d["contributionCount"] for w in weeks for d in w["contributionDays"]}


def fetch_html(user):
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "contrib-level"})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode()
    cell_date = {cid: date for date, cid in
                 re.findall(r'data-date="(\d{4}-\d\d-\d\d)" id="(contribution-day-component-[\d-]+)"', page)}
    tips = dict(re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)</tool-tip>', page))
    days = {}
    for cid, date in cell_date.items():
        m = re.match(r"(\d[\d,]*) contributions?", tips.get(cid, ""))
        days[date] = int(m.group(1).replace(",", "")) if m else 0
    return days


def load_days():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            return fetch_graphql(USER, token)
        except Exception as e:  # fall back to the public calendar
            print(f"graphql failed ({e}), using the public calendar", file=sys.stderr)
    return fetch_html(USER)


def summarise(days):
    dates = sorted(days)
    weeks = []                       # GitHub's calendar weeks start on Sunday
    for d in dates:
        day = dt.date.fromisoformat(d)
        start = day - dt.timedelta(days=(day.weekday() + 1) % 7)
        if not weeks or weeks[-1][0] != start:
            weeks.append([start, 0])
        weeks[-1][1] += days[d]
    streak = best_streak = 0
    for d in dates:
        streak = streak + 1 if days[d] > 0 else 0
        best_streak = max(best_streak, streak)
    best_day = max(dates, key=lambda d: (days[d], d))
    return dict(dates=dates, weeks=weeks, total=sum(days.values()), best_streak=best_streak,
                best_day=(best_day, days[best_day]), best_week=max(w[1] for w in weeks))


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------
def label(font, s, size, x, y, fill, tracking=0.0, anchor="start"):
    """Outlined text when the fonts are around, plain <text> otherwise."""
    try:
        return B.text(font, s, size, x, y, fill, tracking=tracking, anchor=anchor)
    except FileNotFoundError:
        w = len(s) * size * (0.6 + tracking)
        weight = "700" if font.endswith("bold") else "400"
        return (f'<text x="{B.n(x)}" y="{B.n(y)}" font-family="IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, '
                f'Consolas, monospace" font-size="{size}" font-weight="{weight}" letter-spacing="{tracking * size:.2f}" '
                f'text-anchor="{anchor}" fill="{fill}">{html.escape(s)}</text>'), w


# 8 x 10 pixels, facing right. V = headset visor.
SPRITE = ["..HHHH..",
          ".HHHHHH.",
          ".HVVVVVV",
          ".HVVVVVV",
          ".HHHHHH.",
          "..BBBB..",
          ".BBBBBB.",
          "..BBBB.."]
LEGS = (["..L..L..", ".L....L."], ["..L.L...", "..L.L..."])
PX = 2.3


def sprite(th):
    """Feet at (0, 0). Two leg frames that swap while running."""
    col = {"H": th["ink"], "B": th["ink"], "V": th["accent"], "L": th["ink"]}
    rows = SPRITE
    top = -(len(rows) + 2) * PX
    x0 = -4 * PX

    def px(grid, y_off):
        out = []
        for r, row in enumerate(grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    out.append(f'<rect x="{B.n(x0 + c * PX)}" y="{B.n(y_off + r * PX)}" width="{PX + 0.05}" '
                               f'height="{PX + 0.05}" fill="{col[ch]}"/>')
        return "".join(out)

    body = px(rows, top)
    legs = []
    for i, frame in enumerate(LEGS):
        vals = "1;0" if i == 0 else "0;1"
        legs.append(f'<g opacity="{1 if i == 0 else 0}">{px(frame, top + len(rows) * PX)}'
                    f'<animate attributeName="opacity" values="{vals}" dur="0.26s" calcMode="discrete" '
                    f'repeatCount="indefinite"/></g>')
    return body + "".join(legs)


def quad_through(p0, p1, p2, steps=10):
    """Quadratic curve from p0 to p2 that passes through p1 at t = 0.5."""
    c = (2 * p1[0] - (p0[0] + p2[0]) / 2, 2 * p1[1] - (p0[1] + p2[1]) / 2)
    pts = []
    for k in range(1, steps + 1):
        t = k / steps
        a, b, d = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        pts.append((a * p0[0] + b * c[0] + d * p2[0], a * p0[1] + b * c[1] + d * p2[1]))
    return pts


# ---------------------------------------------------------------------------
# the level
# ---------------------------------------------------------------------------
def level(tn, st):
    th = B.THEMES[tn]
    W, H = 1200, 336
    X0, X1 = 44, 1156
    FLOOR, BH = 266, 15
    weeks = st["weeks"]
    nw = len(weeks)
    cw = (X1 - X0) / nw
    tier = lambda c: 0 if c <= 0 else min(7, 1 + int(math.log2(c)))
    tops = [FLOOR - tier(c) * BH for _, c in weeks]
    coins = sorted(sorted(range(nw), key=lambda i: (weeks[i][1], i))[-5:])
    fdefs, fbody, fborder = B.frame(W, H, th, "lv")
    defs = [fdefs, f'<clipPath id="lvclip"><rect x="16" y="60" width="{W - 32}" height="{H - 76}"/></clipPath>']
    body = [fbody]

    # HUD
    x = 44
    lab, lw = label("mono-bold", "LEVEL", 10.5, x, 40, th["accent"], tracking=0.16)
    first, last = dt.date.fromisoformat(st["dates"][0]), dt.date.fromisoformat(st["dates"][-1])
    val, vw = label("mono-bold", f"{first.year}–{str(last.year)[2:]}", 14, x + lw + 10, 40, th["ink"])
    body.append(lab + val)
    x += lw + vw + 46
    stats = [("CONTRIBUTIONS", f"{st['total']:,}"), ("BEST WEEK", str(st["best_week"])),
             ("BEST DAY", str(st["best_day"][1])), ("LONGEST STREAK", f"{st['best_streak']} d")]
    for k, v in stats:
        a, aw = label("mono-bold", k, 10.5, x, 40, th["muted"], tracking=0.14)
        b_, bw = label("mono-bold", v, 14, x + aw + 10, 40, th["ink"])
        body.append(a + b_)
        x += aw + bw + 40
    upd, _ = label("mono", f"updated {last.day} {MONTHS[last.month - 1]} {last.year}", 11, W - 44, 40,
                   th["muted"], anchor="end")
    body.append(upd)
    body.append(f'<rect x="28" y="56" width="{W - 56}" height="1" fill="{th["stroke"]}"/>')

    g = []
    # far background: a 7-day rolling average of the daily counts, as hills
    days = st["dates"]
    counts = [0] * len(days)
    by_date = {d: i for i, d in enumerate(days)}
    for d, c in st["days"].items():
        counts[by_date[d]] = c
    roll = [sum(counts[max(0, i - 6):i + 1]) / min(7, i + 1) for i in range(len(counts))]
    peak = max(roll) or 1
    hx = lambda i: X0 + (X1 - X0) * i / (len(roll) - 1)
    hy = lambda v: FLOOR - 6 - 150 * math.sqrt(v / peak)
    hill = "M" + "L".join(f"{B.n(hx(i))} {B.n(hy(v))}" for i, v in enumerate(roll))
    g.append(f'<path d="{hill}L{X1} {FLOOR}L{X0} {FLOOR}Z" fill="{th["ink"]}" fill-opacity="0.035"/>'
             f'<path d="{hill}" fill="none" stroke="{th["ink"]}" stroke-opacity="0.14" stroke-width="1.2"/>')

    # floor
    g.append(f'<rect x="20" y="{FLOOR}" width="{W - 40}" height="16" fill="{th["ink"]}" fill-opacity="0.07"/>'
             f'<rect x="20" y="{FLOOR}" width="{W - 40}" height="1.5" fill="{th["ink"]}" fill-opacity="0.45"/>')
    bricks = []
    for k in range(int((W - 40) / 22) + 1):
        bx = 20 + k * 22
        bricks.append(f"M{bx} {FLOOR + 1.5}V{FLOOR + 8.5}M{bx + 11} {FLOOR + 8.5}V{FLOOR + 16}")
    g.append(f'<path d="{"".join(bricks)}M20 {FLOOR + 8.5}H{W - 20}" stroke="{th["ink"]}" stroke-opacity="0.12"/>')

    # month labels
    seen = set()
    for i, (start, _) in enumerate(weeks):
        for k in range(7):
            day = start + dt.timedelta(days=k)
            if day.day == 1 and (day.year, day.month) not in seen and first <= day <= last:
                seen.add((day.year, day.month))
                mx = X0 + (i + k / 7) * cw
                txt = str(day.year) if day.month == 1 else MONTHS[day.month - 1]
                colr = th["accent"] if day.month == 1 else th["muted"]
                m_, _ = label("mono", txt, 11, mx + 3, FLOOR + 34, colr)
                g.append(f'<path d="M{B.n(mx)} {FLOOR + 18}V{FLOOR + 25}" stroke="{colr}"/>' + m_)

    # columns
    for i, (_, c) in enumerate(weeks):
        t = tier(c)
        xl = X0 + i * cw
        for k in range(1, t + 1):
            y = FLOOR - k * BH
            top_block = k == t
            hot = top_block and t >= 6
            fill = th["accent"] if hot else th["ink"]
            fo = 0.3 if hot else 0.05 + 0.03 * k
            so = 0.9 if hot else (0.55 if top_block else 0.28)
            g.append(f'<rect x="{B.n(xl + 1)}" y="{B.n(y + 1)}" width="{B.n(cw - 2)}" height="{BH - 2}" rx="2" '
                     f'fill="{fill}" fill-opacity="{fo:.2f}" stroke="{th["accent"] if hot else th["ink"]}" '
                     f'stroke-opacity="{so}"/>')

    # the run: feet positions along column tops, hops between and for coins
    pts = [(X0 + 4, tops[0])]
    coin_at = {}
    for i in range(nw):
        xl, xr, y = X0 + i * cw, X0 + (i + 1) * cw, tops[i]
        if i in coins:                                  # hop for the coin in the middle of the column
            xc = xl + cw / 2
            cy = y - 34
            if pts[-1][0] < xc - 9:
                pts.append((xc - 9, y))
            hop = quad_through((xc - 9, y), (xc, cy + 12), (xc + 9, y), 8)
            coin_at[i] = (xc, cy, len(pts) + 3)
            pts += hop
        if i == nw - 1:
            pts.append((xr - 14, y))
            break
        yn = tops[i + 1]
        if yn == y:
            pts.append((xr, y))
            continue
        if yn < y:                                      # jump up: clear the edge first
            p0, p1, p2 = (xr - 6, y), (xr - 2, yn - 16), (xr + 7, yn)
        else:                                           # hop down
            p0, p1, p2 = (xr - 4, y), (xr + 3, y - 12), (xr + 10, yn)
        if pts[-1][0] < p0[0]:
            pts.append(p0)
        pts += quad_through(p0, p1, p2)

    seg = [math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
    total = sum(seg)
    upto = [0.0]
    for s_ in seg:
        upto.append(upto[-1] + s_)
    SPEED = 135.0
    RUN = total / SPEED
    HOLD = 3.0
    CYC = RUN + HOLD

    # coins, each disappearing when the runner reaches it
    for i, (xc, cy, k) in coin_at.items():
        tc = upto[min(k, len(upto) - 1)] / SPEED
        kt = f"0;{tc / CYC:.4f};1"
        g.append(f'<g transform="translate({B.n(xc)} {B.n(cy)})"><g>'
                 f'<animate attributeName="opacity" values="1;0;0" keyTimes="{kt}" calcMode="discrete" dur="{CYC:.2f}s" repeatCount="indefinite"/>'
                 f'<g><animateTransform attributeName="transform" type="scale" values="1 1;0.25 1;1 1" dur="1.1s" repeatCount="indefinite"/>'
                 f'<path d="M0 -7L6 0L0 7L-6 0Z" fill="{th["accent"]}"/><path d="M0 -3L2.5 0L0 3L-2.5 0Z" fill="{th["bg"]}" opacity="0.5"/></g></g>')
        pop, _ = label("mono-bold", f"+{weeks[i][1]}", 11, 0, -6, th["accent"], anchor="middle")
        g.append(f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;0;0" '
                 f'keyTimes="0;{tc / CYC:.4f};{(tc + 0.05) / CYC:.4f};{(tc + 1.0) / CYC:.4f};1" dur="{CYC:.2f}s" repeatCount="indefinite"/>'
                 f'<animateTransform attributeName="transform" type="translate" values="0 0;0 0;0 -16;0 -16" '
                 f'keyTimes="0;{tc / CYC:.4f};{(tc + 1.0) / CYC:.4f};1" dur="{CYC:.2f}s" repeatCount="indefinite"/>{pop}</g></g>')

    # flag on the current week
    fx, fy = X1 - 4, tops[-1]
    g.append(f'<path d="M{fx} {fy}V{fy - 58}" stroke="{th["ink"]}" stroke-width="2"/>'
             f'<circle cx="{fx}" cy="{fy - 60}" r="2.6" fill="{th["ink"]}"/>'
             f'<path d="M{fx} {fy - 56}L{fx - 26} {fy - 49}L{fx} {fy - 42}Z" fill="{th["accent"]}">'
             f'<animate attributeName="d" values="M{fx} {fy - 56}L{fx - 26} {fy - 49}L{fx} {fy - 42}Z;'
             f'M{fx} {fy - 56}L{fx - 24} {fy - 51}L{fx} {fy - 42}Z;M{fx} {fy - 56}L{fx - 26} {fy - 49}L{fx} {fy - 42}Z" '
             f'dur="0.9s" repeatCount="indefinite"/></path>')
    clear, _ = label("mono-bold", "WEEK CLEAR", 11, fx - 14, fy - 72, th["accent"], tracking=0.14, anchor="end")
    g.append(f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{RUN / CYC:.4f};'
             f'{(RUN + 0.1) / CYC:.4f};1" calcMode="discrete" dur="{CYC:.2f}s" repeatCount="indefinite"/>{clear}</g>')

    # the runner. animateMotion is applied on top of the element's own
    # transform, so the path is relative to the start point.
    sx, sy = pts[0]
    path = "M0 0" + "".join(f"L{B.n(px_ - sx)} {B.n(py_ - sy)}" for px_, py_ in pts[1:])
    g.append(f'<g transform="translate({B.n(sx)} {B.n(sy)})">'
             f'<animateMotion path="{path}" keyPoints="0;1;1" keyTimes="0;{RUN / CYC:.4f};1" calcMode="linear" '
             f'dur="{CYC:.2f}s" repeatCount="indefinite"/>{sprite(th)}</g>')

    body.append(f'<g clip-path="url(#lvclip)">{"".join(g)}</g>')
    body.append(fborder)
    title = (f"My GitHub contributions for the last 12 months as a platformer level: {st['total']:,} contributions, "
             f"best week {st['best_week']}, best day {st['best_day'][1]}, longest streak {st['best_streak']} days.")
    return B.svg(W, H, title, "".join(body), "".join(defs))


def main():
    days = load_days()
    if len(days) < 300:
        sys.exit(f"only {len(days)} days of data, not touching the SVGs")
    st = summarise(days)
    st["days"] = days
    for tn in B.THEMES:
        s = level(tn, st)
        path = os.path.join(OUT, f"level-{tn}.svg")
        with open(path, "w") as f:
            f.write(s)
        print(f"level-{tn}.svg  {len(s) / 1024:.1f} KB  total={st['total']} best_week={st['best_week']} "
              f"streak={st['best_streak']}")


if __name__ == "__main__":
    main()
