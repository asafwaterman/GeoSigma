"""Draw the digitised Atlas readings over their plot pages for checking by eye.

``python scripts/atlas_qa.py <out_dir>`` writes one PNG per plot page: red, blue
and green lines follow the series assigned to the first, second and third date.
"""
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geosigma.extract.atlas_build import PAGES, PDF, SURVEY  # noqa: E402
from geosigma.extract.atlas_profiles import render  # noqa: E402
from geosigma.store import SURVEYS_DIR  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
raw = json.loads((SURVEYS_DIR / SURVEY / "extraction" / "plot_readings.json").read_text())
doc = pymupdf.open(PDF)
colours = [(220, 0, 0), (0, 110, 255), (0, 170, 0)]
for pn, series in raw.items():
    region, line, layout, dates = PAGES[int(pn)]
    im = Image.fromarray(render(doc[int(pn) - 1])).convert("RGB")
    dr = ImageDraw.Draw(im)
    for sr in series:
        k = layout["styles"].index(sr["style"])
        off = 5 * (k - 1)
        pts = [(x + off, y + off) for x, y in sr["pixels"]]
        if len(pts) > 1:
            dr.line(pts, fill=colours[k], width=4)
        for x, y in pts:
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], outline=colours[k], width=2)
    im.resize((im.width // 2, im.height // 2)).save(out / f"atlas_p{int(pn):02d}.png")
