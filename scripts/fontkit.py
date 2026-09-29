"""Text -> SVG path outlines, so the SVGs render identically everywhere
(GitHub shows README SVGs through <img>, which can't load web fonts)."""
import os
from functools import lru_cache

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

# Fonts are not committed (see .gitignore). All three are OFL and on Google
# Fonts: Source Serif 4 (variable), IBM Plex Mono Regular and Bold. Either the
# .woff2 or the .ttf from github.com/google/fonts works.
FONT_DIR = os.environ.get("FONT_DIR", os.path.join(os.path.dirname(__file__), "fonts"))

FONTS = {
    "serif": (("SourceSerif4-Variable.woff2", "SourceSerif4[opsz,wght].ttf"), {"wght": 600, "opsz": 60}),
    "serif-reg": (("SourceSerif4-Variable.woff2", "SourceSerif4[opsz,wght].ttf"), {"wght": 420, "opsz": 28}),
    "mono": (("IBMPlexMono-Regular.woff2", "IBMPlexMono-Regular.ttf"), None),
    "mono-bold": (("IBMPlexMono-Bold.woff2", "IBMPlexMono-Bold.ttf"), None),
}


def _num(v):
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    if s == "-0":
        s = "0"
    return s


class Face:
    def __init__(self, key):
        names, loc = FONTS[key]
        paths = [os.path.join(FONT_DIR, nm) for nm in names]
        found = [p for p in paths if os.path.exists(p)]
        if not found:
            raise FileNotFoundError(f"none of {names} in {FONT_DIR}")
        f = TTFont(found[0])
        if loc:
            f = instancer.instantiateVariableFont(f, loc)
        self.font = f
        self.upm = f["head"].unitsPerEm
        self.cmap = f.getBestCmap()
        self.gs = f.getGlyphSet()
        self.hmtx = f["hmtx"].metrics
        self._kern = self._build_kern()

    def _build_kern(self):
        pairs = {}
        if "GPOS" not in self.font:
            return pairs
        gpos = self.font["GPOS"].table
        kern_lookups = set()
        for fr in gpos.FeatureList.FeatureRecord:
            if fr.FeatureTag == "kern":
                kern_lookups.update(fr.Feature.LookupListIndex)
        for li in sorted(kern_lookups):
            lk = gpos.LookupList.Lookup[li]
            for st in lk.SubTable:
                if lk.LookupType == 9:
                    st = st.ExtSubTable
                if getattr(st, "LookupType", 2) != 2 and lk.LookupType not in (2, 9):
                    continue
                if not hasattr(st, "Format"):
                    continue
                if st.Format == 1:
                    for g1, ps in zip(st.Coverage.glyphs, st.PairSet):
                        for pvr in ps.PairValueRecord:
                            v = getattr(pvr.Value1, "XAdvance", 0) if pvr.Value1 else 0
                            pairs.setdefault((g1, pvr.SecondGlyph), v)
                elif st.Format == 2:
                    c1 = st.ClassDef1.classDefs
                    c2 = st.ClassDef2.classDefs
                    for g1 in st.Coverage.glyphs:
                        k1 = c1.get(g1, 0)
                        row = st.Class1Record[k1]
                        for g2, k2 in c2.items():
                            rec = row.Class2Record[k2]
                            v = getattr(rec.Value1, "XAdvance", 0) if rec.Value1 else 0
                            if v:
                                pairs.setdefault((g1, g2), v)
        return pairs

    def glyph(self, ch):
        return self.cmap.get(ord(ch)) or self.cmap.get(ord("?"))

    def advance(self, text, size, tracking=0.0):
        """Width in px. tracking is in em."""
        s = size / self.upm
        w = 0
        prev = None
        for ch in text:
            g = self.glyph(ch)
            if prev is not None:
                w += self._kern.get((prev, g), 0) * s
            w += self.hmtx[g][0] * s + tracking * size
            prev = g
        return w - (tracking * size if text else 0)

    def glyph_d(self, g):
        """Glyph outline in font units, y flipped so it can be <use>d."""
        pen = SVGPathPen(self.gs, ntos=lambda v: str(round(v)))
        self.gs[g].draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
        return pen.getCommands()

    def layout(self, text, tracking_units=0.0):
        """[(glyph, x_in_font_units)], total advance in units."""
        out = []
        x = 0
        prev = None
        for ch in text:
            g = self.glyph(ch)
            if prev is not None:
                x += self._kern.get((prev, g), 0)
            if ch != " ":
                out.append((g, x))
            x += self.hmtx[g][0] + tracking_units
            prev = g
        return out, x - (tracking_units if text else 0)


@lru_cache(None)
def face(key):
    return Face(key)
