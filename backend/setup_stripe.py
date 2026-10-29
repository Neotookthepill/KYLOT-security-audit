"""Idempotent Stripe catalog setup for KEYLOT. Run once to create products/prices."""
import os
import stripe
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

CATALOG = [
    {
        "emergent_product_id": "keylot_small",
        "name": "QYLOT — Démarrage",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "keylot_small_monthly", "amount": 1900, "currency": "eur", "interval": "month"}],
    },
    {
        "emergent_product_id": "keylot_medium",
        "name": "QYLOT — Active",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "keylot_medium_monthly", "amount": 3900, "currency": "eur", "interval": "month"}],
    },
    {
        "emergent_product_id": "keylot_large",
        "name": "QYLOT — Entreprise",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "keylot_large_monthly", "amount": 6900, "currency": "eur", "interval": "month"}],
    },
]


def get_or_create_product(entry):
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"], tax_code=entry.get("tax_code"),
        metadata={"managed_by": "emergent", "emergent_product_id": entry["emergent_product_id"]},
    )


def ensure_price(product, p):
    existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
    if existing:
        e = existing[0]
        if e.unit_amount != p["amount"] or e.currency != p["currency"]:
            stripe.Price.modify(e.id, active=False)
            existing = []
    if not existing:
        kwargs = dict(product=product.id, unit_amount=p["amount"], currency=p["currency"],
                      lookup_key=p["lookup_key"], transfer_lookup_key=True)
        if p.get("interval"):
            kwargs["recurring"] = {"interval": p["interval"]}
        return stripe.Price.create(**kwargs)
    return existing[0]


def main():
    for entry in CATALOG:
        product = get_or_create_product(entry)
        print(f"Product: {product.name} ({product.id})")
        for p in entry["prices"]:
            price = ensure_price(product, p)
            print(f"  Price: {p['lookup_key']} → {price.id} · {p['amount']/100} {p['currency']}")


if __name__ == "__main__":
    main()
