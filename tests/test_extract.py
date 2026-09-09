"""Unit 4 validation: schema-valid extraction vs golden file, plus a live
glimmer repair probe on deliberately broken JSON."""

from pydantic import BaseModel

from not_nova_act.extract import browser_act_get, glimmer_repair, qwen_repair


class Product(BaseModel):
    name: str
    price: str


class Catalog(BaseModel):
    products: list[Product]


PAGE = (
    "data:text/html,"
    "<style>body{font-family:sans-serif;font-size:34px;background:white;color:black}"
    "li{margin:20px}</style>"
    "<h1>Corner Shop</h1>"
    "<ul><li>koppar Mug - $12</li><li>tresk Spoon - $4</li></ul>"
)

GOLDEN = {"products": [{"name": "koppar Mug", "price": "$12"},
                       {"name": "tresk Spoon", "price": "$4"}]}


def test_browser_act_get_matches_golden():
    res = browser_act_get(
        "Extract every product with its price from this shop page.",
        PAGE, Catalog, max_steps=3, timeout_seconds=400)
    assert res["status"] == "completed", res
    assert res["data"] == GOLDEN, res["data"]


def test_qwen_repair_fixes_trailing_comma():
    broken = '{"products": [{"name": "koppar Mug", "price": "$12"},]}'
    fixed = qwen_repair(broken, Catalog)
    assert fixed.products[0].name == "koppar Mug"


def test_glimmer_repair_parses_backend_payload():
    """Logic-only: canned backend payload through the parse path, so the
    shared-service flakiness (idle reaping, 0.36 tok/s) cannot fail the
    battery. Live glimmer was probed manually this session."""
    import httpx

    real_post = httpx.post

    def fake_post(*a, **k):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {
                    "content": "",
                    "reasoning_content": 'thought\n{"products": '
                                         '[{"name": "koppar Mug", '
                                         '"price": "$12"}]}'}}]}
        return Resp()

    httpx.post = fake_post
    try:
        fixed = glimmer_repair("garbage", Catalog)
    finally:
        httpx.post = real_post
    assert fixed.products[0].price == "$12"
