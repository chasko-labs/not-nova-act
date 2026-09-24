"""keeper_qc on synthetic fixtures: no network, no models, pure pixels."""

from PIL import Image, ImageDraw, ImageFont

from not_nova_act.keeper_qc import edge_crop, key_purity, score_keeper, text_blobs


def _panel(path, draw_fn, size=(336, 288), bg=(18, 22, 40)):
    im = Image.new("RGB", size, bg)
    draw_fn(ImageDraw.Draw(im), size)
    im.save(path)
    return str(path)


def test_edge_crop_fails_on_touching_subject(tmp_path):
    p = _panel(tmp_path / "touch.png",
               lambda d, s: d.rectangle([50, 50, s[0] - 1, 200], fill=(240, 200, 60)))
    out = edge_crop(p, min_margin=8)
    assert out["status"] == "completed", out
    assert out["pass"] is False, out
    assert out["margins"]["right"] == 0, out


def test_edge_crop_passes_with_clearance(tmp_path):
    p = _panel(tmp_path / "clear.png",
               lambda d, s: d.rectangle([30, 30, s[0] - 30, 200], fill=(240, 200, 60)))
    out = edge_crop(p, min_margin=8)
    assert out["status"] == "completed", out
    assert out["pass"] is True, out
    assert min(out["margins"].values()) >= 8, out


def test_text_blobs_finds_drawn_caption(tmp_path):
    def draw(d, s):
        d.rectangle([20, 200, s[0] - 20, 260], fill=(5, 5, 20))
        d.text((40, 215), "FARE $38.16 PER DAY", fill=(255, 255, 255),
               font=ImageFont.load_default(size=24))
    p = _panel(tmp_path / "caption.png", draw)
    out = text_blobs(p, max_clusters=0)
    assert out["status"] == "completed", out
    assert out["pass"] is False and out["clusters"] >= 1, out


def test_text_blobs_clean_on_flat_panel(tmp_path):
    p = _panel(tmp_path / "flat.png",
               lambda d, s: d.ellipse([80, 60, 256, 220], fill=(120, 120, 130)))
    out = text_blobs(p, max_clusters=0)
    assert out["status"] == "completed", out
    assert out["pass"] is True, out


def test_text_blobs_region_gate_counts_raw_regions(tmp_path):
    def draw(d, s):
        d.rectangle([20, 200, s[0] - 20, 260], fill=(5, 5, 20))
        d.text((40, 215), "FARE $38.16 PER DAY", fill=(255, 255, 255),
               font=ImageFont.load_default(size=24))
    p = _panel(tmp_path / "caption.png", draw)
    tight = text_blobs(p, region=(20, 200, 316, 260), max_clusters=99,
                       max_regions=5)
    assert tight["status"] == "completed", tight
    assert tight["pass"] is False and tight["regions"] > 5, tight
    loose = text_blobs(p, region=(20, 200, 316, 260), max_clusters=99,
                       max_regions=500)
    assert loose["pass"] is True, loose


def test_key_purity_passes_on_green_plate(tmp_path):
    p = _panel(tmp_path / "green.png",
               lambda d, s: d.rectangle([100, 80, 236, 208], fill=(240, 200, 60)),
               bg=(20, 200, 40))
    out = key_purity(p, min_keyable=0.25)
    assert out["status"] == "completed", out
    assert out["pass"] is True and out["keyable"] > 0.5, out


def test_key_purity_fails_on_night_scene(tmp_path):
    p = _panel(tmp_path / "night.png",
               lambda d, s: d.rectangle([100, 80, 236, 208], fill=(240, 200, 60)))
    out = key_purity(p, min_keyable=0.25)
    assert out["status"] == "completed", out
    assert out["pass"] is False, out


def test_score_keeper_aggregates_and_never_raises(tmp_path):
    p = _panel(tmp_path / "good.png",
               lambda d, s: d.rectangle([30, 30, s[0] - 30, 200], fill=(240, 200, 60)))
    out = score_keeper(p, {"min_margin": 8, "max_text_clusters": 2})
    assert out["status"] == "completed", out
    assert out["pass"] is True, out
    bad = score_keeper(str(tmp_path / "missing.png"), {"min_margin": 8})
    assert bad["checks"]["edge_crop"]["status"] == "error", bad
    assert bad["pass"] is False, bad
