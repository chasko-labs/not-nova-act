"""Unit 5: CLIP re-rank assist. Cached weights only, CPU, offline.
Re-rank only — never plans. Used on low confidence or duplicate names."""

from __future__ import annotations

import io
import os
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")

CLIP_MODEL_ID = os.environ.get("NOT_NOVA_ACT_CLIP_MODEL", "openai/clip-vit-base-patch32")

_model = None
_processor = None


def _load():
    global _model, _processor
    if _model is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        _processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID, local_files_only=True)
        _model = CLIPModel.from_pretrained(CLIP_MODEL_ID, local_files_only=True)
        _model.eval()
    return _model, _processor


def score_crops(expression: str, crops: list) -> list[float]:
    """Cosine-ish CLIP logit per crop for the expression. CPU, no GPU."""
    import torch

    model, processor = _load()
    inputs = processor(text=[expression] * len(crops), images=crops,
                       return_tensors="pt", padding=True)
    with torch.no_grad():
        out = model(**inputs)
    # rank crops against each other: softmax down the image dim
    return out.logits_per_image.softmax(dim=0)[:, 0].tolist()


def rerank_candidates(expression: str, screenshot_png: bytes,
                      candidates: list[dict[str, Any]], pad: int = 8) -> list[dict[str, Any]]:
    """Sort candidates by CLIP relevance to the expression. Returns new list
    with `clip_score` attached; never raises (returns input order on error)."""
    try:
        from PIL import Image

        shot = Image.open(io.BytesIO(screenshot_png)).convert("RGB")
        crops = []
        usable = []
        for c in candidates:
            box = c.get("box") or {}
            x, y, w, h = (int(box.get(k, 0)) for k in ("x", "y", "width", "height"))
            if w <= 0 or h <= 0:
                continue
            crop = shot.crop((max(0, x - pad), max(0, y - pad),
                              x + w + pad, y + h + pad))
            crops.append(crop)
            usable.append(c)
        if not usable:
            return candidates
        scores = score_crops(expression, crops)
        ranked = sorted(zip(scores, usable), key=lambda t: t[0], reverse=True)
        return [{**c, "clip_score": round(s, 4)} for s, c in ranked]
    except Exception:
        return candidates
