"""Deterministic keeper-panel QC: pure pixels, no agent vision, no model.

Machine-readable version of the scorecard gates a human eye was doing:
- edge_crop: subject bbox vs frame edges (bumper-crop, sticker-on-edge)
- text_blobs: MSER glyph-cluster detector (roof-sign scribble, plaque text)
- key_purity: greenscreen keyability (non-uniform bg, spill)

Every entry returns a dict and never raises, per analyze.py convention.
"""

from __future__ import annotations

from typing import Any


def _load(path: str):
    import cv2
    import numpy as np

    im = cv2.imread(path, cv2.IMREAD_COLOR)
    if im is None:
        return None, None
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return im, blur


def _bg_mask(blur, tol: int = 14):
    """Background = pixels flood-connected to any frame edge."""
    import cv2
    import numpy as np

    h, w = blur.shape
    bg = np.zeros((h + 2, w + 2), dtype=np.uint8)
    for y in range(0, h, 4):
        for x in (0, w - 1):
            if not bg[y + 1, x + 1]:
                _, _, bg, _ = cv2.floodFill(
                    blur.copy(), bg, (x, y), 255, tol, tol,
                    cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    for x in range(0, w, 4):
        for y in (0, h - 1):
            if not bg[y + 1, x + 1]:
                _, _, bg, _ = cv2.floodFill(
                    blur.copy(), bg, (x, y), 255, tol, tol,
                    cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    return bg[1:-1, 1:-1]


def edge_crop(path: str, min_margin: int = 8,
              tol: int = 14) -> dict[str, Any]:
    """Subject bbox margins per side. Pass when all clear min_margin."""
    import cv2
    import numpy as np

    try:
        im, blur = _load(path)
        if im is None:
            return {"status": "error", "error_message": "unreadable image"}
        h, w = blur.shape
        bg = _bg_mask(blur, tol)
        subj = (bg == 0).astype(np.uint8) * 255
        subj = cv2.morphologyEx(
            subj, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        ys, xs = np.nonzero(subj)
        if len(xs) == 0:
            # everything is edge-connected (subject touches frame or
            # empty panel): zero clearance on all sides, fails any margin.
            margins = {"left": 0, "top": 0, "right": 0, "bottom": 0}
            return {"status": "completed",
                    "pass": min_margin <= 0, "margins": margins,
                    "min_margin": min_margin,
                    "detail": "subject edge-connected throughout"}
        margins = {"left": int(xs.min()), "top": int(ys.min()),
                   "right": int(w - 1 - xs.max()),
                   "bottom": int(h - 1 - ys.max())}
        ok = all(m >= min_margin for m in margins.values())
        return {"status": "completed", "pass": ok, "margins": margins,
                "min_margin": min_margin}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


def text_blobs(path: str, region: tuple | None = None,
               max_clusters: int = 0,
               max_regions: int | None = None) -> dict[str, Any]:
    """MSER glyph-cluster detector. Regions with line structure count as
    text-like; pass when cluster count <= max_clusters and (when given)
    raw region count <= max_regions. Region is an optional
    (x0, y0, x1, y1) crop to inspect. Whole cartoon panels always carry
    texture regions (checker stripes, stars), so scope the gate to the
    band where model text appears (e.g. roof-sign band) and calibrate
    max_regions there: clean taxi-v6 reads 12, scribbled v8 reads 64."""
    import cv2
    import numpy as np

    try:
        im, blur = _load(path)
        if im is None:
            return {"status": "error", "error_message": "unreadable image"}
        if region is not None:
            x0, y0, x1, y1 = region
            blur = blur[y0:y1, x0:x1]
        mser = cv2.MSER_create(5, 25, 3000, 0.35)
        regions, _ = mser.detectRegions(blur)
        boxes = []
        for pts in regions:
            x, y, w, h = cv2.boundingRect(pts)
            if h < 6 or h > 120 or w < 4:
                continue
            aspect = w / max(h, 1)
            if 0.1 <= aspect <= 8.0 and w * h >= 60:
                boxes.append((x, y, w, h))
        # cluster boxes into text lines by vertical overlap
        boxes.sort(key=lambda b: b[1])
        lines: list[list] = []
        for b in boxes:
            placed = False
            for line in lines:
                ly = sum(l[1] + l[3] / 2 for l in line) / len(line)
                lh = sum(l[3] for l in line) / len(line)
                if abs((b[1] + b[3] / 2) - ly) < lh * 0.7:
                    line.append(b)
                    placed = True
                    break
            if not placed:
                lines.append([b])
        clusters = sum(1 for line in lines if len(line) >= 2)
        ok = clusters <= max_clusters
        if max_regions is not None:
            ok = ok and len(boxes) <= max_regions
        return {"status": "completed", "pass": ok,
                "clusters": clusters, "max_clusters": max_clusters,
                "regions": len(boxes), "max_regions": max_regions}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


def key_purity(path: str, min_keyable: float = 0.25) -> dict[str, Any]:
    """Greenscreen keyability: fraction of frame that is border-connected
    green-dominant. Pass when >= min_keyable."""
    import cv2
    import numpy as np

    try:
        im, _ = _load(path)
        if im is None:
            return {"status": "error", "error_message": "unreadable image"}
        h, w = im.shape[:2]
        b, g, r = (im[:, :, i].astype(np.int16) for i in range(3))
        green = (g > 110) & (g - r > 35) & (g - b > 25)
        gm = green.astype(np.uint8) * 255
        n, lab, stats, _ = cv2.connectedComponentsWithStats(gm, 8)
        keyable_px = 0
        for ci in range(1, n):
            cx, cy, cw, ch, _ = stats[ci]
            if cx == 0 or cy == 0 or cx + cw == w or cy + ch == h:
                keyable_px += np.count_nonzero(lab == ci)
        keyable = float(keyable_px) / (h * w)
        return {"status": "completed", "pass": keyable >= min_keyable,
                "keyable": round(keyable, 3), "min_keyable": min_keyable}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


def score_keeper(path: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Run the spec'd gates. Spec keys: min_margin, max_text_clusters,
    text_region, min_keyable. Omitted gates are skipped."""
    try:
        checks: dict[str, Any] = {}
        if "min_margin" in spec:
            checks["edge_crop"] = edge_crop(path, spec["min_margin"])
        if "max_text_clusters" in spec or "max_text_regions" in spec:
            checks["text_blobs"] = text_blobs(
                path, spec.get("text_region"),
                spec.get("max_text_clusters", 10 ** 9),
                spec.get("max_text_regions"))
        if "min_keyable" in spec:
            checks["key_purity"] = key_purity(path, spec["min_keyable"])
        ok = all(c.get("status") == "completed" and c.get("pass")
                 for c in checks.values()) and bool(checks)
        return {"status": "completed", "pass": ok, "checks": checks}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}
