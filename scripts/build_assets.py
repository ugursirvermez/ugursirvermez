"""Generates every SVG under assets/ (dark + light pairs).

    pip install fonttools brotli
    python3 scripts/build_assets.py


All text is converted to outlines (see fontkit.py) and every animation is
SMIL, because GitHub serves README images through <img>: no scripts, no web
fonts, but SMIL + CSS inside the SVG still run.

Rule used throughout: an element's *static* attributes describe the final,
fully-visible state. Animations start at t=0 and only override that, so a
renderer that ignores animation (GitHub mobile, some previews) still shows a
complete image.
"""
import math
import os
import sys

from fontkit import face

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "assets")

THEMES = {
    "dark": dict(
        bg="#0f1013", stroke="#272a31", dot="#ffffff", dotop=0.05,
        ink="#ece8e1", muted="#8d8980", faint="#34363d",
        accent="#f2464a", red="#ff4747", cyan="#2fd3d8", blend="screen",
    ),
    "light": dict(
        bg="#f6f3ec", stroke="#d9d2c4", dot="#000000", dotop=0.06,
        ink="#17171b", muted="#6b665d", faint="#d3ccbe",
        accent="#d7263d", red="#e5303d", cyan="#0096a8", blend="multiply",
    ),
}
# Game "screens" stay dark in both themes, like a monitor would.
SCREEN = dict(bg="#0b0c0f", ink="#ece8e1", muted="#8d8980", faint="#2b2d33",
              accent="#f2464a", red="#ff4747", cyan="#2fd3d8")


def n(v):
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s == "-0" else s


# Glyphs used by the SVG currently being built. Each glyph outline is stored
# once in <defs> and placed with <use>, which keeps text-heavy files small.
_GLYPHS = {}
_FONT_IDS = {"serif": "s", "serif-reg": "r", "mono": "m", "mono-bold": "b"}


def text(font, s, size, x, y, fill, tracking=0.0, anchor="start", attrs=""):
    f = face(font)
    runs, adv = f.layout(s, tracking * f.upm)
    scale = size / f.upm
    w = adv * scale
    if anchor == "middle":
        x -= w / 2
    elif anchor == "end":
        x -= w
    uses = []
    for g, gx in runs:
        gid = f"{_FONT_IDS[font]}{f.font.getGlyphID(g):x}"
        if gid not in _GLYPHS:
            _GLYPHS[gid] = f.glyph_d(g)
        uses.append(f'<use href="#{gid}" x="{round(gx)}"/>')
    tr = f"translate({n(x)} {n(y)}) scale({scale:.5g})"
    return f'<g transform="{tr}" fill="{fill}"{(" " + attrs) if attrs else ""}>{"".join(uses)}</g>', w


def width(font, s, size, tracking=0.0):
    return face(font).advance(s, size, tracking)


def svg(w, h, title, body, defs=""):
    glyphs = "".join(f'<path id="{k}" d="{v}"/>' for k, v in sorted(_GLYPHS.items()))
    _GLYPHS.clear()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t"><title id="t">{title}</title>'
        f"<defs>{glyphs}{defs}</defs>{body}</svg>\n"
    )


def frame(w, h, th, uid, r=20):
    """Card background: rounded panel + dot grid."""
    defs = (
        f'<pattern id="{uid}dots" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<circle cx="12" cy="12" r="1" fill="{th["dot"]}" fill-opacity="{th["dotop"]}"/></pattern>'
        f'<clipPath id="{uid}card"><rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{r}"/></clipPath>'
    )
    body = (
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{r}" fill="{th["bg"]}"/>'
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{r}" fill="url(#{uid}dots)"/>'
    )
    border = f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{r}" fill="none" stroke="{th["stroke"]}"/>'
    return defs, body, border


# --------------------------------------------------------------------------
# 3D helpers
# --------------------------------------------------------------------------
PHI = (1 + 5 ** 0.5) / 2
ICO_V = []
for a in (-1, 1):
    for b in (-PHI, PHI):
        ICO_V += [(0, a, b), (a, b, 0), (b, 0, a)]
ICO_E = [(i, j) for i in range(12) for j in range(i + 1, 12)
         if abs(sum((ICO_V[i][k] - ICO_V[j][k]) ** 2 for k in range(3)) - 4) < 1e-6]
assert len(ICO_E) == 30

CUBE_V = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
CUBE_E = [(i, j) for i in range(8) for j in range(i + 1, 8)
          if sum(abs(CUBE_V[i][k] - CUBE_V[j][k]) for k in range(3)) == 2]


def strokes(edges):
    """Split an edge list into as few polylines as possible (greedy walk).
    Fewer 'M' commands = smaller path strings, and the structure stays the
    same every frame so SMIL can interpolate 'd'."""
    left = {tuple(e) for e in edges}
    adj = {}
    for a, b in left:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    out = []
    while left:
        odd = [v for v in adj if len(adj[v]) % 2 == 1]
        v = odd[0] if odd else next(v for v in adj if adj[v])
        line = [v]
        while adj[v]:
            u = min(adj[v])
            adj[v].discard(u)
            adj[u].discard(v)
            left.discard((min(u, v), max(u, v)))
            line.append(u)
            v = u
        out.append(line)
    return out


def rot(p, axis, ang):
    x, y, z = p
    ux, uy, uz = axis
    c, s = math.cos(ang), math.sin(ang)
    dot = ux * x + uy * y + uz * z
    cx, cy, cz = uy * z - uz * y, uz * x - ux * z, ux * y - uy * x
    return (x * c + cx * s + ux * dot * (1 - c),
            y * c + cy * s + uy * dot * (1 - c),
            z * c + cz * s + uz * dot * (1 - c))


def norm(v):
    l = math.sqrt(sum(c * c for c in v))
    return tuple(c / l for c in v)


def wire_frames(verts, edges, frames, cx, cy, px_radius, axis, tilt=0.0, eye=0.0, dist=6.0):
    """Perspective-projected wireframe, one path string per frame.
    eye = horizontal eye offset for stereo (zero parallax at object centre)."""
    r = max(math.sqrt(sum(c * c for c in v)) for v in verts)
    f = px_radius * dist / r
    lines = strokes(edges)
    axis = norm(axis)
    out = []
    for i in range(frames):
        ang = 2 * math.pi * i / frames
        pts = []
        for v in verts:
            p = rot(v, (1, 0, 0), tilt)
            p = rot(p, axis, ang)
            Z = dist + p[2]
            sx = cx + f * (p[0] - eye) / Z + f * eye / dist
            sy = cy - f * p[1] / Z
            pts.append((sx, sy))
        d = "".join("M" + "L".join(f"{n(pts[k][0])} {n(pts[k][1])}" for k in ln) for ln in lines)
        out.append(d)
    return out


def anim_d(frames, dur, extra=""):
    vals = ";".join(frames + [frames[0]])
    return f'<animate attributeName="d" values="{vals}" dur="{dur}s" repeatCount="indefinite"{extra}/>'


def discrete(attr, vals, times, dur, extra=""):
    """times are absolute seconds within dur; converted to keyTimes."""
    kt = ";".join(f"{t / dur:.4f}" for t in times)
    vv = ";".join(str(v) for v in vals)
    return (f'<animate attributeName="{attr}" values="{vv}" keyTimes="{kt}" dur="{dur}s" '
            f'calcMode="discrete" repeatCount="indefinite"{extra}/>')


def typing_loop(phrases, cw, t_char=0.045, hold=2.3, t_erase=0.018, gap=0.35, first_hold=2.8):
    """Typewriter timeline. Phrase 0 is fully typed at t=0 and the cycle ends
    by typing it again, so the loop is seamless and a frozen t=0 frame reads."""
    tracks = [[(0.0, 0.0)] for _ in phrases]
    k0 = len(phrases[0])
    tracks[0] = [(0.0, k0 * cw)]
    t = first_hold
    for j in range(1, k0 + 1):
        tracks[0].append((t + j * t_erase, (k0 - j) * cw))
    t += k0 * t_erase + gap
    for i, s in enumerate(phrases[1:], 1):
        k = len(s)
        for j in range(1, k + 1):
            tracks[i].append((t + j * t_char, j * cw))
        t += k * t_char + hold
        for j in range(1, k + 1):
            tracks[i].append((t + j * t_erase, (k - j) * cw))
        t += k * t_erase + gap
    for j in range(1, k0 + 1):
        tracks[0].append((t + j * t_char, j * cw))
    return t + k0 * t_char + 0.05, tracks


# --------------------------------------------------------------------------
# HERO
# --------------------------------------------------------------------------
def hero(tn):
    th = THEMES[tn]
    W, H = 1200, 420
    uid = "h"
    fdefs, fbody, fborder = frame(W, H, th, uid)
    defs = [fdefs]
    body = [fbody]

    # ---- left column -----------------------------------------------------
    x0 = 64
    lbl, _ = text("mono-bold", "PHD · COMPUTER & INSTRUCTIONAL TECHNOLOGIES", 13, x0, 118,
                  th["accent"], tracking=0.14)
    body.append(lbl)

    name, nw = text("serif", "Uğur Sırvermez", 78, x0 - 3, 200, th["ink"])
    ghosts = []
    for col, dx in ((th["red"], -9), (th["cyan"], 9)):
        g, _ = text("serif", "Uğur Sırvermez", 78, x0 - 3, 200, col)
        ghosts.append(
            f'<g opacity="0" style="mix-blend-mode:{th["blend"]}">'
            f'<animateTransform attributeName="transform" type="translate" values="{dx} 0;{dx} 0;0 0" '
            f'keyTimes="0;0.3;1" calcMode="spline" keySplines="0 0 1 1;0.25 0.8 0.25 1" dur="1.5s" fill="freeze"/>'
            f'<animate attributeName="opacity" values="0.95;0.95;0" keyTimes="0;0.75;1" dur="1.5s" fill="freeze"/>'
            f'{g}</g>')
    body.append(f'<g style="isolation:isolate">{name}{"".join(ghosts)}</g>')

    body.append(f'<rect x="{x0}" y="224" width="56" height="3" fill="{th["accent"]}">'
                f'<animate attributeName="width" values="0;0;56" keyTimes="0;0.6;1" dur="1.7s" '
                f'calcMode="spline" keySplines="0 0 1 1;0.2 0.7 0.2 1" fill="freeze"/></rect>')

    # typed line
    size = 19
    cw = width("mono", "a", size)
    prompt, pw = text("mono-bold", ">", size, x0, 276, th["accent"])
    tx = x0 + pw + cw * 0.6
    phrases = [
        "game engines as learning environments",
        "VR / AR prototypes in Unity & C#",
        "PyTorch → ONNX → Unity Sentis",
        "digital citizenship & AI literacy",
        "teaching Unity to people who say 'hocam'",
    ]
    cycle, tracks = typing_loop(phrases, cw)
    body.append(prompt)
    caret_ev = {}
    for i, (s, ev) in enumerate(zip(phrases, tracks)):
        p, _ = text("mono", s, size, tx, 276, th["ink"])
        full = len(s) * cw
        base = full if i == 0 else 0
        defs.append(f'<clipPath id="hty{i}"><rect x="{tx}" y="252" height="32" width="{n(base)}">'
                    + discrete("width", [n(w) for _, w in ev], [t for t, _ in ev], round(cycle, 3))
                    + "</rect></clipPath>")
        body.append(f'<g clip-path="url(#hty{i})">{p}</g>')
        for t, w in ev[1:]:
            caret_ev[t] = w
    times = [0.0] + sorted(caret_ev)
    xs = [n(tx + len(phrases[0]) * cw)] + [n(tx + caret_ev[t]) for t in sorted(caret_ev)]
    body.append(
        f'<rect x="{n(tx + len(phrases[0]) * cw + 2)}" y="259" width="{n(cw * 0.55)}" height="22" fill="{th["accent"]}">'
        + discrete("x", xs, times, round(cycle, 3))
        + '<animate attributeName="opacity" values="1;0" dur="1s" calcMode="discrete" repeatCount="indefinite"/>'
        + "</rect>")

    row, _ = text("mono", "research   /   unity & xr   /   teaching", 14, x0, 336, th["muted"])
    body.append(row)

    # ---- right column: the scene ----------------------------------------
    sx, sy, sw, sh = 660, 40, 500, 320
    hz = 250                      # horizon
    cx = sx + sw / 2
    defs.append(f'<clipPath id="hscene"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="4"/></clipPath>')
    defs.append(
        '<linearGradient id="hfv" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="0.35" stop-color="#fff" stop-opacity="0.55"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>'
        '<linearGradient id="hfh" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#000" stop-opacity="1"/>'
        '<stop offset="0.22" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="0.78" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="1"/></linearGradient>'
        f'<mask id="hfloor" maskUnits="userSpaceOnUse" x="{sx}" y="{hz}" width="{sw}" height="{sy+sh-hz}">'
        f'<rect x="{sx}" y="{hz}" width="{sw}" height="{sy+sh-hz}" fill="url(#hfv)"/>'
        f'<rect x="{sx}" y="{hz}" width="{sw}" height="{sy+sh-hz}" fill="url(#hfh)"/></mask>'
        '<filter id="hblur" x="-50%" y="-200%" width="200%" height="500%"><feGaussianBlur stdDeviation="14"/></filter>'
    )
    scene = []
    # horizon glow
    scene.append(f'<ellipse cx="{cx}" cy="{hz}" rx="210" ry="16" fill="{th["accent"]}" opacity="0.22" filter="url(#hblur)">'
                 '<animate attributeName="opacity" values="0.22;0.3;0.22" dur="5s" repeatCount="indefinite"/></ellipse>')
    # floor
    floor = []
    k_near, depth_scale = 0.9, 110.0     # y = hz + depth_scale / z
    bottom = sy + sh
    for j in range(-9, 10):
        k = 1.3   # extend a bit past the bottom edge; the clip hides the rest
        floor.append(f'<line x1="{cx}" y1="{hz}" x2="{n(cx + j * 72 * k)}" y2="{n(hz + (bottom - hz) * k)}"/>')
    K, dz, P = 12, 1.15, 0.55
    zfar = k_near + K * dz
    samples = 16
    for k in range(K):
        ys = []
        for s in range(samples + 1):
            z = zfar - (zfar - k_near) * s / samples
            ys.append(n(hz + depth_scale / z))
        y_static = hz + depth_scale / (zfar - (zfar - k_near) * (k + 0.5) / K)
        floor.append(f'<rect x="{sx}" y="{n(y_static)}" width="{sw}" height="1.1" stroke="none" fill="{th["ink"]}">'
                     f'<animate attributeName="y" values="{";".join(ys)}" dur="{n(K * P)}s" '
                     f'begin="-{n(k * P)}s" repeatCount="indefinite"/></rect>')
    scene.append(f'<g mask="url(#hfloor)" stroke="{th["ink"]}" stroke-width="1" opacity="0.5">{"".join(floor)}</g>')
    scene.append(f'<line x1="{sx}" y1="{hz}" x2="{sx+sw}" y2="{hz}" stroke="{th["accent"]}" stroke-opacity="0.45"/>')

    # shadow under the die
    ocx, ocy, orad = cx, 150, 78
    scene.append(f'<ellipse cx="{ocx}" cy="300" rx="62" ry="7" fill="{th["ink"]}" opacity="0.13">'
                 '<animate attributeName="rx" values="62;52;62" dur="4s" calcMode="spline" '
                 'keySplines="0.45 0 0.55 1;0.45 0 0.55 1" repeatCount="indefinite"/></ellipse>')

    # anaglyph d20
    NF, DUR = 48, 16
    axis = (0.35, 1.0, 0.18)
    eye = 0.34
    left = wire_frames(ICO_V, ICO_E, NF, ocx, ocy, orad, axis, tilt=0.35, eye=-eye / 2)
    right = wire_frames(ICO_V, ICO_E, NF, ocx, ocy, orad, axis, tilt=0.35, eye=+eye / 2)
    glitch_l = ('<animateTransform attributeName="transform" type="translate" values="0 0;0 0;5 0;-3 0;0 0;0 0" '
                'keyTimes="0;0.88;0.9;0.915;0.93;1" dur="7s" repeatCount="indefinite"/>')
    glitch_r = glitch_l.replace("5 0;-3 0", "-5 0;3 0")
    die = (
        f'<g style="isolation:isolate">'
        f'<g style="mix-blend-mode:{th["blend"]}">{glitch_l}<path d="{left[0]}" fill="none" stroke="{th["red"]}" '
        f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round">{anim_d(left, DUR)}</path></g>'
        f'<g style="mix-blend-mode:{th["blend"]}">{glitch_r}<path d="{right[0]}" fill="none" stroke="{th["cyan"]}" '
        f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round">{anim_d(right, DUR)}</path></g>'
        f'</g>'
    )
    scene.append('<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -9;0 0" '
                 'dur="4s" calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1" repeatCount="indefinite"/>'
                 + die + "</g>")

    body.append(f'<g clip-path="url(#hscene)">{"".join(scene)}</g>')

    # viewfinder brackets + HUD
    b = 16
    br = []
    for (px, py, dx, dy) in [(sx, sy, 1, 1), (sx + sw, sy, -1, 1), (sx, sy + sh, 1, -1), (sx + sw, sy + sh, -1, -1)]:
        br.append(f"M{px} {py + dy * b}V{py}H{px + dx * b}")
    body.append(f'<path d="{"".join(br)}" fill="none" stroke="{th["muted"]}" stroke-width="1.5"/>')

    hud_l, _ = text("mono", "STEREO  L/R", 11, sx + 34, sy + 26, th["muted"], tracking=0.1)
    body.append(f'<circle cx="{sx + 24}" cy="{sy + 22}" r="3.5" fill="{th["accent"]}">'
                '<animate attributeName="opacity" values="1;0.2;1" dur="1.6s" repeatCount="indefinite"/></circle>' + hud_l)
    ms_vals = ["11.1 ms", "10.8 ms", "11.0 ms", "9.7 ms", "11.1 ms", "10.9 ms"]
    hz_lbl, hzw = text("mono", "/ 90 Hz", 11, sx + sw - 20, sy + 26, th["muted"], anchor="end", tracking=0.05)
    body.append(hz_lbl)
    step = 0.4
    for i, v in enumerate(ms_vals):
        p, _ = text("mono", v, 11, sx + sw - 26 - hzw, sy + 26, th["ink"], anchor="end", tracking=0.05)
        vals = [1 if j == i else 0 for j in range(len(ms_vals))]
        body.append(f'<g opacity="{1 if i == 0 else 0}">{p}'
                    + discrete("opacity", vals, [j * step for j in range(len(ms_vals))], step * len(ms_vals))
                    + "</g>")

    cap, _ = text("mono", "fig. 1 — a d20 as a red/cyan anaglyph. glasses optional.", 12, sx, 394, th["muted"])
    body.append(cap)

    body.append(fborder)
    return svg(W, H, "Uğur Sırvermez — game engines, virtual environments, machine learning",
               "".join(body), "".join(defs))


# --------------------------------------------------------------------------
# PLAY CARD
# --------------------------------------------------------------------------
def octagon(r):
    pts = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        pts.append(f"{n(r * math.cos(a))},{n(r * math.sin(a))}")
    return " ".join(pts)


def play(tn):
    th = THEMES[tn]
    S = SCREEN
    W, H = 1200, 300
    uid = "p"
    fdefs, fbody, fborder = frame(W, H, th, uid)
    defs = [fdefs]
    body = [fbody]

    # ---- screen ------------------------------------------------------------
    X, Y, SW, SH = 22, 22, 540, 256
    cx, cy = X + SW / 2, Y + SH / 2
    defs.append(f'<clipPath id="pscr"><rect x="{X}" y="{Y}" width="{SW}" height="{SH}" rx="12"/></clipPath>')
    defs.append(
        '<radialGradient id="pfog"><stop offset="0" stop-color="#0b0c0f" stop-opacity="1"/>'
        '<stop offset="1" stop-color="#0b0c0f" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="pvig" cx="0.5" cy="0.5" r="0.62">'
        '<stop offset="0.55" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.85"/>'
        '<animate attributeName="r" values="0.62;0.5;0.62" dur="5s" calcMode="spline" '
        'keySplines="0.45 0 0.55 1;0.45 0 0.55 1" repeatCount="indefinite"/></radialGradient>'
    )
    scr = [f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" fill="{S["bg"]}"/>']

    tunnel = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        tunnel.append(f'<line x1="0" y1="0" x2="{n(420 * math.cos(a))}" y2="{n(420 * math.sin(a))}" '
                      f'stroke="{S["ink"]}" stroke-opacity="0.18" stroke-width="1"/>')
    RD, NR = 3.2, 12
    spline = 'calcMode="spline" keyTimes="0;1" keySplines="0.6 0 0.97 0.55"'
    for k in range(NR):
        tunnel.append(
            f'<g opacity="0"><polygon points="{octagon(42)}" fill="none" stroke="{S["ink"]}" stroke-width="0.6"/>'
            f'<animateTransform attributeName="transform" type="scale" values="0.05;5" {spline} '
            f'dur="{RD}s" begin="-{n(k * RD / NR)}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0.9;0.9;0" keyTimes="0;0.4;0.92;1" '
            f'dur="{RD}s" begin="-{n(k * RD / NR)}s" repeatCount="indefinite"/></g>')
    body_rot = ('<animateTransform attributeName="transform" type="rotate" values="0;45" dur="16s" '
                'repeatCount="indefinite"/>')
    scr.append(f'<g transform="translate({cx} {cy})"><g>{body_rot}{"".join(tunnel)}</g>')

    # gates (red rings) and one judder cube, flying past off-centre
    def flyer(inner, dx, dy, begin, dur=RD):
        return (f'<g opacity="0"><animateTransform attributeName="transform" type="translate" values="0 0;{dx} {dy}" '
                f'{spline} dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.35;0.9;1" dur="{dur}s" '
                f'begin="{begin}s" repeatCount="indefinite"/>'
                f'<g><animateTransform attributeName="transform" type="scale" values="0.05;5" {spline} '
                f'dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>{inner}</g></g>')

    gate = (f'<circle r="18" fill="none" stroke="{S["accent"]}" stroke-width="0.9"/>'
            f'<circle r="21" fill="none" stroke="{S["accent"]}" stroke-width="0.3" stroke-opacity="0.6"/>')
    scr.append(flyer(gate, 90, -30, -0.4))
    scr.append(flyer(gate, -70, 45, -2.0))
    cube_l = wire_frames(CUBE_V, CUBE_E, 1, 0, 0, 9, (0.4, 1, 0.2), tilt=0.5, eye=-0.25)[0]
    cube_r = wire_frames(CUBE_V, CUBE_E, 1, 0, 0, 9, (0.4, 1, 0.2), tilt=0.5, eye=0.25)[0]
    cube = (f'<g style="isolation:isolate"><path d="{cube_l}" fill="none" stroke="{S["red"]}" stroke-width="0.5" '
            f'style="mix-blend-mode:screen"/><path d="{cube_r}" fill="none" stroke="{S["cyan"]}" stroke-width="0.5" '
            f'style="mix-blend-mode:screen"/></g>')
    scr.append(flyer(cube, -150, -60, -1.1, dur=RD * 1.25))
    scr.append(flyer(cube, 160, 70, -3.1, dur=RD * 1.25))

    scr.append('<circle r="26" fill="url(#pfog)"/>')
    # reticle
    ret = (f'<g><circle r="11" fill="none" stroke="{S["accent"]}" stroke-width="1.6"/>'
           f'<path d="M-18 0H-6M6 0H18M0 -18V-6M0 6V18" stroke="{S["accent"]}" stroke-width="1.6"/>'
           f'<circle r="1.8" fill="{S["accent"]}"/>'
           '<animateMotion dur="9s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.6 1" '
           'path="M0,0 C70,-50 130,10 90,40 C50,70 -40,60 -90,20 C-130,-10 -80,-60 -30,-40 C0,-28 -10,-8 0,0Z"/></g>')
    scr.append(ret + "</g>")
    scr.append(f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" fill="url(#pvig)"/>')

    # HUD
    lab, lw = text("mono-bold", "NAUSEA", 10.5, X + 18, Y + 26, S["muted"], tracking=0.12)
    scr.append(lab)
    levels = [1, 1, 2, 2, 3, 5, 5, 4, 6, 7, 7, 3, 2, 2]
    step = 0.6
    for s in range(10):
        vals = [1 if lv > s else 0.18 for lv in levels]
        col = S["accent"] if s >= 6 else S["ink"]
        scr.append(f'<rect x="{n(X + 26 + lw + s * 9)}" y="{Y + 17}" width="6" height="10" fill="{col}" '
                   f'opacity="{vals[0]}">' + discrete("opacity", vals, [i * step for i in range(len(levels))],
                                                      step * len(levels)) + "</rect>")
    fps, _ = text("mono", "11.1 ms · 90 Hz", 10.5, X + SW - 18, Y + 26, S["muted"], anchor="end", tracking=0.06)
    scr.append(fps)
    gl, _ = text("mono", "GATES", 10.5, X + 18, Y + SH - 18, S["muted"], tracking=0.12)
    scr.append(gl)
    counts = ["07", "08", "09", "10", "11", "12", "13"]
    for i, c in enumerate(counts):
        p, _ = text("mono-bold", c, 10.5, X + 70, Y + SH - 18, S["ink"], tracking=0.1)
        vals = [1 if j == i else 0 for j in range(len(counts))]
        scr.append(f'<g opacity="{1 if i == 0 else 0}">{p}'
                   + discrete("opacity", vals, [j * RD / 2 for j in range(len(counts))], RD / 2 * len(counts))
                   + "</g>")
    cm, _ = text("mono", "comfort vignette: on", 10.5, X + SW - 18, Y + SH - 18, S["muted"], anchor="end")
    scr.append(cm)

    body.append(f'<g clip-path="url(#pscr)">{"".join(scr)}</g>')
    body.append(f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" rx="12" fill="none" stroke="{th["stroke"]}"/>')

    # ---- right side ----------------------------------------------------------
    rx = 600
    l1, _ = text("mono-bold", "PLAYABLE EXPLAINER · VR COMFORT", 12, rx, 64, th["accent"], tracking=0.14)
    body.append(l1)
    t1, _ = text("serif", "Tunnel Vision", 56, rx - 2, 126, th["ink"])
    body.append(t1)
    for i, line in enumerate(["A small game about VR sickness: vection,",
                              "comfort vignettes, the 11.1 ms frame budget.",
                              "Play a round, then read the notes it teaches."]):
        p, _ = text("mono", line, 15, rx, 166 + i * 23, th["muted"])
        body.append(p)

    bx, by, bw, bh = rx, 222, 212, 46
    body.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="none" stroke="{th["accent"]}" stroke-width="2">'
                f'<animate attributeName="stroke-opacity" values="0.8;0" dur="1.8s" repeatCount="indefinite"/>'
                f'<animate attributeName="x" values="{bx};{bx-9}" dur="1.8s" repeatCount="indefinite"/>'
                f'<animate attributeName="y" values="{by};{by-9}" dur="1.8s" repeatCount="indefinite"/>'
                f'<animate attributeName="width" values="{bw};{bw+18}" dur="1.8s" repeatCount="indefinite"/>'
                f'<animate attributeName="height" values="{bh};{bh+18}" dur="1.8s" repeatCount="indefinite"/></rect>')
    body.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="{th["accent"]}"/>')
    lab, lw = text("mono-bold", "PRESS START", 16, bx + bw / 2 + 12, by + 29, "#fff", anchor="middle", tracking=0.12)
    tri_x = bx + bw / 2 - lw / 2 - 8
    tri = f'<path d="M{n(tri_x - 11)} {by + 16}L{n(tri_x)} {by + 23}L{n(tri_x - 11)} {by + 30}Z" fill="#fff"/>'
    body.append(f'<g>{tri}{lab}<animate attributeName="opacity" values="1;1;0.25;1" keyTimes="0;0.55;0.75;1" '
                f'dur="1.4s" repeatCount="indefinite"/></g>')
    h1, _ = text("mono", "mouse · touch · WASD", 12.5, bx + bw + 26, by + 18, th["muted"])
    h2, _ = text("mono", "C vignette · V stereo · N notes", 12.5, bx + bw + 26, by + 38, th["muted"])
    body.append(h1 + h2)

    body.append(fborder)
    return svg(W, H, "Tunnel Vision — a playable explainer about VR comfort. Press start.", "".join(body), "".join(defs))


# --------------------------------------------------------------------------
# FEATURED: GameEngineStudio (course site)
# --------------------------------------------------------------------------
def feature(tn):
    """Echoes the course's own demo: the same pendulum model, first as a
    simulation, then as a game (a goal and feedback added, model unchanged)."""
    th = THEMES[tn]
    S = SCREEN
    W, H = 1200, 300
    fdefs, fbody, fborder = frame(W, H, th, "g")
    defs = [fdefs]
    body = [fbody]
    X, Y, SW, SH = 22, 22, 540, 256
    defs.append(f'<clipPath id="gscr"><rect x="{X}" y="{Y}" width="{SW}" height="{SH}" rx="12"/></clipPath>'
                f'<pattern id="ggrid" width="20" height="20" patternUnits="userSpaceOnUse">'
                f'<path d="M20 0H0V20" fill="none" stroke="{S["ink"]}" stroke-opacity="0.06"/></pattern>')
    scr = [f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" fill="{S["bg"]}"/>',
           f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" fill="url(#ggrid)"/>']
    CYC = 10.0          # 0-5 s simulation, 5-10 s game
    def phase(game, inner):
        v = [0, 1, 0] if game else [1, 0, 1]
        return (f'<g opacity="{1 if not game else 0}">{inner}'
                + discrete("opacity", v, [0, CYC / 2, CYC], CYC) + "</g>")

    # tabs
    tx, ty = X + 20, Y + 20
    t1, w1 = text("mono-bold", "simulation", 12, tx + 12, ty + 19, S["ink"])
    t2, w2 = text("mono-bold", "game", 12, tx + w1 + 44, ty + 19, S["ink"])
    tab_w1, tab_w2 = w1 + 24, w2 + 24
    scr.append(f'<rect x="{tx}" y="{ty}" width="{n(tab_w1 + tab_w2 + 8)}" height="28" rx="7" fill="none" '
               f'stroke="{S["faint"]}"/>')
    scr.append(f'<rect x="{tx + 3}" y="{ty + 3}" width="{n(tab_w1 - 4)}" height="22" rx="5" fill="{S["accent"]}">'
               + discrete("x", [tx + 3, n(tx + tab_w1 + 5), tx + 3], [0, CYC / 2, CYC], CYC)
               + discrete("width", [n(tab_w1 - 4), n(tab_w2 - 4), n(tab_w1 - 4)], [0, CYC / 2, CYC], CYC)
               + "</rect>")
    scr.append(t1 + t2)
    pl, _ = text("mono", "Earth  ·  Moon  ·  Mars", 11, X + SW - 20, ty + 19, S["muted"], anchor="end")
    scr.append(pl)

    # pendulum
    px, py, L, amp = X + SW / 2, Y + 70, 128, 32
    scr.append(f'<path d="M{px - 34} {py}H{px + 34}" stroke="{S["muted"]}" stroke-width="2"/>')
    ends = [(px + L * math.sin(math.radians(a)), py + L * math.cos(math.radians(a))) for a in (-amp, amp)]
    scr.append(f'<path d="M{n(ends[0][0])} {n(ends[0][1])}A{L} {L} 0 0 0 {n(ends[1][0])} {n(ends[1][1])}" '
               f'fill="none" stroke="{S["ink"]}" stroke-opacity="0.25" stroke-dasharray="3 5"/>')
    # game phase: a target zone near the right end of the swing
    a0, a1 = math.radians(20), math.radians(29)
    tz = (f'<path d="M{n(px + L * math.sin(a0))} {n(py + L * math.cos(a0))}A{L} {L} 0 0 0 '
          f'{n(px + L * math.sin(a1))} {n(py + L * math.cos(a1))}" fill="none" stroke="{S["accent"]}" '
          f'stroke-width="12" stroke-opacity="0.35" stroke-linecap="round"/>')
    goal, _ = text("mono", "stop the bob inside the red zone", 11, px, Y + SH - 44, S["muted"], anchor="middle")
    sc, _ = text("mono-bold", "3 / 5", 12, X + SW - 20, Y + SH - 20, S["accent"], anchor="end")
    scr.append(phase(True, tz + goal + sc))
    sim_note, _ = text("mono", "change L and g, watch the period", 11, px, Y + SH - 44, S["muted"], anchor="middle")
    scr.append(phase(False, sim_note))
    sw_ = (f'<animateTransform attributeName="transform" type="rotate" values="{amp} {px} {py};{-amp} {px} {py};{amp} {px} {py}" '
           f'calcMode="spline" keyTimes="0;0.5;1" keySplines="0.37 0 0.63 1;0.37 0 0.63 1" dur="2.4s" repeatCount="indefinite"/>')
    scr.append(f'<g>{sw_}<path d="M{px} {py}V{py + L}" stroke="{S["ink"]}" stroke-width="1.6"/>'
               f'<circle cx="{px}" cy="{py + L}" r="13" fill="{S["bg"]}" stroke="{S["ink"]}" stroke-width="2"/>'
               f'<circle cx="{px}" cy="{py + L}" r="4" fill="{S["accent"]}"/></g>')
    scr.append(f'<circle cx="{px}" cy="{py}" r="3.5" fill="{S["ink"]}"/>')
    eq, _ = text("serif-reg", "θ'' = −(g / L) · sin θ", 17, X + 20, Y + SH - 18, S["ink"])
    scr.append(eq)
    body.append(f'<g clip-path="url(#gscr)">{"".join(scr)}</g>')
    body.append(f'<rect x="{X}" y="{Y}" width="{SW}" height="{SH}" rx="12" fill="none" stroke="{th["stroke"]}"/>')

    rx = 600
    l1, _ = text("mono-bold", "FEATURED · COURSE SITE · LIVE", 12, rx, 64, th["accent"], tracking=0.14)
    t1, _ = text("serif", "GameEngineStudio", 52, rx - 2, 124, th["ink"])
    body.append(l1 + t1)
    for i, line in enumerate(["Course site for Modeling & Design in Education:",
                              "14 weeks of Unity 6 for future teachers, with",
                              "demos you can poke at right in the browser."]):
        p, _ = text("mono", line, 15, rx, 164 + i * 23, th["muted"])
        body.append(p)
    bx, by, bw, bh = rx, 222, 240, 46
    body.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="{th["ink"]}"/>')
    lab, _ = text("mono-bold", "↗  OPEN THE COURSE", 15, bx + bw / 2, by + 29, th["bg"], anchor="middle", tracking=0.1)
    body.append(lab)
    h1, _ = text("mono", "in Turkish · Unity 6", 12.5, bx + bw + 26, by + 18, th["muted"])
    h2, _ = text("mono", "2025–26 fall term", 12.5, bx + bw + 26, by + 38, th["muted"])
    body.append(h1 + h2)
    body.append(fborder)
    return svg(W, H, "GameEngineStudio — course site for Modeling and Design in Education. Open the course.",
               "".join(body), "".join(defs))


# --------------------------------------------------------------------------
# PROJECT CARDS
# --------------------------------------------------------------------------
def card(tn, uid, title, lines, meta, illus, alt):
    th = THEMES[tn]
    W, H = 600, 280
    fdefs, fbody, fborder = frame(W, H, th, uid, r=16)
    defs = [fdefs]
    body = [fbody]
    tsize = 30 if width("serif", title, 30) < 290 else 30 * 290 / width("serif", title, 30)
    t, _ = text("serif", title, tsize, 30, 66, th["ink"])
    body.append(t)
    body.append(f'<rect x="30" y="82" width="28" height="2.5" fill="{th["accent"]}"/>')
    for i, line in enumerate(lines):
        p, _ = text("mono", line, 13, 30, 118 + i * 22, th["muted"])
        body.append(p)
    m, _ = text("mono-bold", meta, 11, 30, 246, th["ink"], tracking=0.08)
    body.append(m)
    idefs, ibody = illus(th, uid)
    defs.append(idefs)
    body.append(f'<g clip-path="url(#{uid}card)">{ibody}</g>')
    body.append(fborder)
    return svg(W, H, alt, "".join(body), "".join(defs))


def illus_fbc(th, uid):
    S = SCREEN
    X, Y, W, H = 322, 30, 250, 188
    defs = (f'<clipPath id="{uid}crt"><rect x="{X}" y="{Y}" width="{W}" height="{H}" rx="14"/></clipPath>'
            f'<pattern id="{uid}scan" width="4" height="3" patternUnits="userSpaceOnUse">'
            f'<rect width="4" height="1" fill="#000" fill-opacity="0.45"/></pattern>'
            f'<radialGradient id="{uid}glow" cx="0.5" cy="0.5" r="0.7"><stop offset="0.6" stop-color="#000" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="#000" stop-opacity="0.7"/></radialGradient>')
    p = [f'<rect x="{X}" y="{Y}" width="{W}" height="{H}" fill="{S["bg"]}"/>']
    lines = [
        ("FEDERAL BUREAU OF CONTROL", "mono-bold", S["ink"]),
        ("OLDEST HOUSE · TERMINAL 04", "mono", S["muted"]),
        ("", None, None),
        ("> open hotline.archive", "mono", S["ink"]),
        ("  auth ........ ok", "mono", S["muted"]),
        ("  ACCESS GRANTED", "mono-bold", S["accent"]),
        ("> read memo_1968.txt", "mono", S["ink"]),
    ]
    size = 11
    cw = width("mono", "a", size)
    tx, ty0, ldy = X + 16, Y + 28, 18.5
    t = 0.3
    dur = 11.0
    caret_pos = []
    for i, (s, fnt, col) in enumerate(lines):
        if not s:
            continue
        y = ty0 + i * ldy
        path, _ = text(fnt, s, size, tx, y, col)
        k = len(s)
        speed = 0.035 if s.startswith(">") else 0.012
        ev_t = [0.0] + [t + j * speed for j in range(1, k + 1)] + [dur - 0.4]
        ev_w = [0] + [n(j * cw) for j in range(1, k + 1)] + [0]
        for tt, ww in zip(ev_t[1:-1], ev_w[1:-1]):
            caret_pos.append((tt, tx + float(ww), y))
        defs += (f'<clipPath id="{uid}l{i}"><rect x="{tx}" y="{y - 12}" height="16" width="{n(k * cw)}">'
                 + discrete("width", ev_w, ev_t, dur) + "</rect></clipPath>")
        p.append(f'<g clip-path="url(#{uid}l{i})">{path}</g>')
        t += k * speed + (0.5 if s.startswith(">") else 0.15)
    # redacted bars appear after the memo command
    for j, (bw_, off) in enumerate([(150, 0), (96, 60)]):
        y = ty0 + (7 + j) * ldy - 9
        p.append(f'<rect x="{tx + off}" y="{y}" width="{bw_}" height="10" fill="{S["ink"]}" opacity="0">'
                 + discrete("opacity", [0, 0.85, 0], [0, t + 0.25 * j, dur - 0.4], dur) + "</rect>")
    t_after = t + 0.9
    # caret
    ct = [0.0] + [c[0] for c in caret_pos] + [t_after, dur - 0.4]
    last = caret_pos[-1]
    cx_ = [n(tx)] + [n(c[1]) for c in caret_pos] + [n(tx), n(tx)]
    cy_ = [n(ty0 - 10)] + [n(c[2] - 10) for c in caret_pos] + [n(ty0 + 10 * ldy - 10), n(ty0 - 10)]
    p.append(f'<rect x="{n(last[1])}" y="{n(last[2] - 10)}" width="{n(cw)}" height="12" fill="{S["accent"]}">'
             + discrete("x", cx_, ct, dur) + discrete("y", cy_, ct, dur)
             + '<animate attributeName="opacity" values="1;0" dur="0.9s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    p.append(f'<rect x="{X}" y="{Y}" width="{W}" height="{H}" fill="url(#{uid}scan)"/>')
    p.append(f'<rect x="{X}" y="{Y}" width="{W}" height="{H}" fill="url(#{uid}glow)"/>')
    p.append(f'<rect x="{X}" y="{Y}" width="{W}" height="{H}" fill="#fff" opacity="0">'
             '<animate attributeName="opacity" values="0;0;0.05;0;0.03;0" keyTimes="0;0.6;0.62;0.64;0.66;1" '
             'dur="4.3s" repeatCount="indefinite"/></rect>')
    body = (f'<g clip-path="url(#{uid}crt)">{"".join(p)}</g>'
            f'<rect x="{X}" y="{Y}" width="{W}" height="{H}" rx="14" fill="none" stroke="{th["stroke"]}"/>')
    return defs, body


def illus_torch(th, uid):
    X0, Y0, X1, Y1 = 340, 44, 566, 206
    p = []
    for i in range(1, 4):
        y = Y0 + (Y1 - Y0) * i / 4
        p.append(f'<line x1="{X0}" y1="{n(y)}" x2="{X1}" y2="{n(y)}" stroke="{th["faint"]}" stroke-dasharray="2 4"/>')
    p.append(f'<path d="M{X0} {Y0}V{Y1}H{X1}" fill="none" stroke="{th["muted"]}" stroke-width="1.2"/>')
    lo, _ = text("mono", "loss", 11, X0 + 6, Y0 + 4, th["muted"])
    ep, _ = text("mono", "epoch", 11, X1, Y1 + 16, th["muted"], anchor="end")
    p.append(lo + ep)
    import random
    rnd = random.Random(7)
    pts = []
    val_pts = []
    N = 44
    for i in range(N + 1):
        u = i / N
        loss = 0.08 + 0.92 * math.exp(-4.2 * u) + rnd.uniform(-0.035, 0.035) * (1 - 0.6 * u)
        val = 0.14 + 0.86 * math.exp(-3.4 * u) + 0.06 * u * u + rnd.uniform(-0.02, 0.02)
        x = X0 + 6 + (X1 - X0 - 12) * u
        pts.append((x, Y1 - 6 - (Y1 - Y0 - 20) * min(loss, 1)))
        val_pts.append((x, Y1 - 6 - (Y1 - Y0 - 20) * min(val, 1)))
    d = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
    dv = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in val_pts)
    L = sum(math.dist(pts[i], pts[i + 1]) for i in range(N)) + 5
    Lv = sum(math.dist(val_pts[i], val_pts[i + 1]) for i in range(N)) + 5
    dur = 6
    draw = lambda LL: (f'<animate attributeName="stroke-dashoffset" values="{n(LL)};{n(LL)};0;0;{n(LL)}" '
                       f'keyTimes="0;0.05;0.6;0.92;1" dur="{dur}s" repeatCount="indefinite"/>')
    p.append(f'<path d="{dv}" fill="none" stroke="{th["cyan"]}" stroke-width="1.4" stroke-dasharray="3 3" '
             f'opacity="0.9"><animate attributeName="opacity" values="0;0;0.9;0.9;0" keyTimes="0;0.05;0.6;0.92;1" '
             f'dur="{dur}s" repeatCount="indefinite"/></path>')
    p.append(f'<path d="{d}" fill="none" stroke="{th["accent"]}" stroke-width="2.2" stroke-linejoin="round" '
             f'stroke-linecap="round" stroke-dasharray="{n(L)}" stroke-dashoffset="0">{draw(L)}</path>')
    lg1, _ = text("mono", "train", 10.5, X1 - 64, Y0 + 4, th["accent"])
    lg2, _ = text("mono", "val", 10.5, X1 - 22, Y0 + 4, th["cyan"])
    p.append(lg1 + lg2)
    code, _ = text("mono-bold", "loss.backward()", 12, X0, Y1 + 36, th["ink"])
    p.append(code)
    return "", "".join(p)


def illus_nms(th, uid):
    cx, cy = 452, 138
    p = []
    # face, line art
    p.append(f'<ellipse cx="{cx}" cy="{cy}" rx="44" ry="54" fill="none" stroke="{th["ink"]}" stroke-width="1.6"/>')
    p.append(f'<circle cx="{cx - 16}" cy="{cy - 10}" r="3.2" fill="{th["ink"]}"/>'
             f'<circle cx="{cx + 16}" cy="{cy - 10}" r="3.2" fill="{th["ink"]}"/>')
    p.append(f'<path d="M{cx - 15} {cy + 22}Q{cx} {cy + 32} {cx + 15} {cy + 22}" fill="none" stroke="{th["ink"]}" stroke-width="1.6" stroke-linecap="round"/>')
    p.append(f'<path d="M{cx - 2} {cy - 2}L{cx - 5} {cy + 10}H{cx + 2}" fill="none" stroke="{th["ink"]}" stroke-width="1.2" stroke-linejoin="round"/>')
    # six-keypoint dots (BlazeFace predicts 6)
    for kx, ky in [(-16, -10), (16, -10), (0, 6), (0, 26), (-40, -2), (40, -2)]:
        p.append(f'<circle cx="{cx + kx}" cy="{cy + ky}" r="2.2" fill="{th["cyan"]}" opacity="0.9"/>')
    boxes = [(-58, -70, 118, 138, 0.61), (-52, -62, 102, 128, 0.83), (-66, -78, 128, 146, 0.72),
             (-48, -58, 100, 122, 0.97), (-60, -64, 110, 134, 0.88), (-54, -76, 114, 146, 0.55)]
    best = 3
    dur = 6.0
    for i, (dx, dy, w, h, sc) in enumerate(boxes):
        t_in = 0.3 + i * 0.28
        if i == best:
            col = th["accent"]
            op = [0, 0, 1, 1, 0]
            tt = [0, t_in, t_in + 0.2, dur - 0.5, dur - 0.2]
            sw = 2.2
        else:
            col = th["cyan"]
            op = [0, 0, 0.75, 0.75, 0, 0]
            tt = [0, t_in, t_in + 0.2, 2.6, 3.0, dur - 0.1]
            sw = 1.1
        kt = ";".join(f"{v / dur:.3f}" for v in tt)
        p.append(f'<rect x="{cx + dx}" y="{cy + dy}" width="{w}" height="{h}" rx="3" fill="none" stroke="{col}" '
                 f'stroke-width="{sw}" opacity="{1 if i == best else 0}">'
                 f'<animate attributeName="opacity" values="{";".join(map(str, op))}" keyTimes="{kt}" '
                 f'dur="{dur}s" repeatCount="indefinite"/></rect>')
    bx, by = cx + boxes[best][0], cy + boxes[best][1]
    lb, lw = text("mono-bold", "face 0.97", 10.5, bx + 6, by - 6, "#fff")
    p.append(f'<g><rect x="{bx}" y="{by - 18}" width="{n(lw + 12)}" height="16" rx="2" fill="{th["accent"]}"/>{lb}'
             f'<animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;0.5;0.53;0.92;0.97" '
             f'dur="{dur}s" repeatCount="indefinite"/></g>')
    cap1, _ = text("mono", "6 candidates", 11, 340, 246, th["muted"])
    cap2, _ = text("mono", "→ NMS →", 11, 440, 246, th["muted"])
    cap3, _ = text("mono-bold", "1 face", 11, 510, 246, th["accent"])
    p.append(cap1 + cap2 + cap3)
    return "", "".join(p)


def illus_mla(th, uid):
    """ML-Agents maze: BFS gives the route the 'trained' agent takes."""
    cols, rows, c = 7, 5, 30
    X0, Y0 = 346, 40
    blocked = {(1, 1), (1, 2), (1, 3), (3, 0), (3, 1), (3, 3), (3, 4), (5, 1), (5, 2), (5, 3), (5, 4)}
    start, goal = (0, 4), (6, 4)
    prev = {start: None}
    q = [start]
    while q:
        cur = q.pop(0)
        if cur == goal:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cur[0] + dx, cur[1] + dy
            if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in blocked and (nx, ny) not in prev:
                prev[(nx, ny)] = cur
                q.append((nx, ny))
    route = []
    cur = goal
    while cur:
        route.append(cur)
        cur = prev[cur]
    route.reverse()
    assert route[0] == start
    ctr = lambda p: (X0 + p[0] * c + c / 2, Y0 + p[1] * c + c / 2)
    p = [f'<rect x="{X0}" y="{Y0}" width="{cols * c}" height="{rows * c}" fill="none" stroke="{th["muted"]}" stroke-width="1.2"/>']
    for i in range(1, cols):
        p.append(f'<path d="M{X0 + i * c} {Y0}V{Y0 + rows * c}" stroke="{th["faint"]}"/>')
    for j in range(1, rows):
        p.append(f'<path d="M{X0} {Y0 + j * c}H{X0 + cols * c}" stroke="{th["faint"]}"/>')
    for (bx, by) in blocked:
        p.append(f'<rect x="{X0 + bx * c + 3}" y="{Y0 + by * c + 3}" width="{c - 6}" height="{c - 6}" rx="2" '
                 f'fill="{th["ink"]}" fill-opacity="0.8"/>')
    gx, gy = ctr(goal)
    p.append(f'<rect x="{gx - 9}" y="{gy - 9}" width="18" height="18" rx="3" fill="none" stroke="{th["cyan"]}" stroke-width="2"/>')
    pts = [ctr(r) for r in route]
    d = "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts)
    Lp = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    dur = 7.0
    run = 0.7
    p.append(f'<path d="{d}" fill="none" stroke="{th["accent"]}" stroke-width="2" stroke-opacity="0.45" '
             f'stroke-dasharray="{n(Lp)}" stroke-dashoffset="0"><animate attributeName="stroke-dashoffset" '
             f'values="{n(Lp)};0;0;{n(Lp)}" keyTimes="0;{run};0.95;1" dur="{dur}s" repeatCount="indefinite"/></path>')
    sx, sy = pts[0]
    rel = "M0 0" + "".join(f"L{n(x - sx)} {n(y - sy)}" for x, y in pts[1:])
    p.append(f'<circle cx="{n(sx)}" cy="{n(sy)}" r="7" fill="{th["accent"]}">'
             f'<animateMotion path="{rel}" keyPoints="0;1;1;0" keyTimes="0;{run};0.95;1" calcMode="linear" '
             f'dur="{dur}s" repeatCount="indefinite"/></circle>')
    rw, _ = text("mono-bold", "+1.0", 12, gx, gy - 20, th["cyan"], anchor="middle")
    p.append(f'<g opacity="0">{rw}<animate attributeName="opacity" values="0;0;1;1;0" '
             f'keyTimes="0;{run};{run + 0.03};0.9;0.95" dur="{dur}s" repeatCount="indefinite"/></g>')
    ep, _ = text("mono", "episode 4812 · mean reward 0.93", 11, X0, Y0 + rows * c + 26, th["muted"])
    p.append(ep)
    return "", "".join(p)


CARDS = {
    "mla": dict(title="Unity-ML-Test-Project",
                lines=["A Unity ML-Agents test: an agent", "trained to find its way through",
                       "a maze to a target point."],
                meta="C# · UNITY ML-AGENTS", illus=illus_mla,
                alt="Unity-ML-Test-Project: an ML-Agents agent walks a maze to its goal"),
    "fbc": dict(title="FBC_OS",
                lines=["A fictional FBC terminal from", "Remedy's Control. CRT glow, audio",
                       "logs, a hotline archive. Fan work."],
                meta="PYTHON · RETRO UI", illus=illus_fbc,
                alt="FBC_OS: a retro terminal inspired by Control"),
    "torch": dict(title="PyTorch_Education",
                  lines=["PyTorch course notes in Turkish,", "from tensors to a model running",
                         "on a phone. Citable via Zenodo."],
                  meta="JUPYTER · DOI 10.5281/ZENODO.19015554", illus=illus_torch,
                  alt="PyTorch_Education: a training loss curve being drawn"),
    "nms": dict(title="BlazeFace_NMS_Sentis",
                lines=["BlazeFace running in Unity Sentis,", "with non-max suppression moved",
                       "out of the ONNX graph into Unity."],
                meta="ONNX · UNITY SENTIS", illus=illus_nms,
                alt="BlazeFace_NMS_Sentis: six candidate boxes reduced to one by NMS"),
}


# --------------------------------------------------------------------------
# FOOTER
# --------------------------------------------------------------------------
def footer(tn):
    th = THEMES[tn]
    W, H = 1200, 96
    fdefs, fbody, fborder = frame(W, H, th, "f", r=14)
    body = [fbody]
    x0, y0 = 28, 38
    fname, fw = text("mono-bold", "thesis.unity", 12, x0, y0, th["ink"], tracking=0.04)
    body.append(fname)
    dur = 13.0
    msgs = [
        ("Importing assets (2113/2114)…", 0.0),
        ("Compiling shader variants…", 3.2),
        ("Baking lightmaps · almost there", 6.2),
        ("Baking lightmaps · 99%", 9.0),
        ("Rebuilding lighting cache", 12.1),
    ]
    for i, (m, t0) in enumerate(msgs):
        t1 = msgs[i + 1][1] if i + 1 < len(msgs) else dur
        p, _ = text("mono", m, 12, x0 + fw + 16, y0, th["muted"])
        vals, times = ([1, 0], [0, t1]) if i == 0 else ([0, 1, 0], [0, t0, t1])
        if t1 >= dur:
            vals, times = [0, 1], [0, t0]
        body.append(f'<g opacity="{1 if i == 0 else 0}">{p}{discrete("opacity", vals, times, dur)}</g>')
    bw = 560
    body.append(f'<rect x="{x0}" y="{y0 + 16}" width="{bw}" height="6" rx="3" fill="{th["faint"]}"/>')
    fills = "0;0.18;0.42;0.63;0.86;0.97;0.99;0.99;0.03;0"
    kts = "0;0.1;0.24;0.4;0.6;0.7;0.9;0.93;0.94;1"
    vals = ";".join(n(bw * float(v)) for v in fills.split(";"))
    body.append(f'<rect x="{x0}" y="{y0 + 16}" width="{n(bw * 0.97)}" height="6" rx="3" fill="{th["accent"]}">'
                f'<animate attributeName="width" values="{vals}" keyTimes="{kts}" dur="{dur}s" repeatCount="indefinite"/></rect>')
    r1, _ = text("serif-reg", "Thanks for scrolling this far.", 19, W - 28, 44, th["ink"], anchor="end")
    r2, _ = text("mono", "ugursirvermez@hotmail.com", 12, W - 28, 66, th["muted"], anchor="end")
    body.append(r1 + r2)
    body.append(fborder)
    return svg(W, H, "A Unity progress bar that never quite finishes. Thanks for scrolling this far.",
               "".join(body), fdefs)


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = []
    for tn in THEMES:
        jobs.append((f"hero-{tn}.svg", lambda tn=tn: hero(tn)))
        jobs.append((f"play-{tn}.svg", lambda tn=tn: play(tn)))
        jobs.append((f"feature-{tn}.svg", lambda tn=tn: feature(tn)))
        jobs.append((f"footer-{tn}.svg", lambda tn=tn: footer(tn)))
        for key, c in CARDS.items():
            jobs.append((f"card-{key}-{tn}.svg",
                         lambda tn=tn, key=key, c=c: card(tn, key, c["title"], c["lines"], c["meta"], c["illus"], c["alt"])))
    for name, fn in jobs:
        s = fn()
        with open(os.path.join(OUT, name), "w") as f:
            f.write(s)
        print(f"{name:26} {len(s) / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
