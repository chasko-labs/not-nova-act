"""T3 act_get: structured extract vs golden file, pydantic-validated."""

from pydantic import BaseModel

from not_nova_act.extract import browser_act_get


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


def test_t3_act_get():
    res = browser_act_get(
        "Extract every product with its price from this shop page.",
        PAGE, Catalog, max_steps=3, timeout_seconds=400)
    assert res["status"] == "completed", res
    assert res["data"] == GOLDEN, res["data"]
