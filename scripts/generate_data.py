"""Generate deterministic commerce data as CSV, optionally with planted defects.

Two modes exist so that every data quality rule can be seen both ways:

* ``clean``   - no rule should fire. A rule that fires here is a false positive.
* ``defects`` - known defects are planted, and their row IDs are written to a
  ground-truth manifest. A rule that misses one is a false negative.

The optional ``--s3-bucket`` flag uploads the same files to the bucket used by the
Snowflake stages in ``sql/setup/04_stages_and_file_format.sql``.
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from faker import Faker

COUNTRIES = ["NG", "GH", "KE", "ZA", "GB", "US"]
STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
SCALES = {
    "small": {"customers": 2_000, "products": 200, "orders": 10_000},
    "full": {"customers": 10_000, "products": 500, "orders": 50_000},
}
CATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Tablets", "Accessories"],
    "Clothing": ["Shirts", "Trainers", "Dresses", "Outerwear"],
    "Home": ["Furniture", "Kitchen", "Bedding", "Lighting"],
    "Beauty": ["Skincare", "Haircare", "Fragrance", "Makeup"],
    "Sports": ["Gym", "Outdoors", "Cycling", "Swimming"],
}
# Rows set aside so a planted customer or product defect never creates an
# accidental orphan downstream, which would blur the ground truth.
RESERVED_CUSTOMERS = 40
RESERVED_PRODUCTS = 20


def _uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _timestamp(rng: random.Random, now: datetime, max_days: int) -> datetime:
    return now - timedelta(seconds=rng.randint(3_600, max_days * 86_400))


def generate_clean(seed: int, scale: str, now: datetime) -> dict[str, list[dict]]:
    """Return clean rows for each entity. All values are strings, as in a raw feed."""
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    size = SCALES[scale]

    customers = []
    for i in range(size["customers"]):
        created = _timestamp(rng, now, 365)
        customers.append(
            {
                "src_row_id": i + 1,
                "customer_id": _uuid(rng),
                "email": f"user{i + 1}@{fake.free_email_domain()}",
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "country": rng.choice(COUNTRIES),
                "created_at": created.isoformat(timespec="seconds"),
            }
        )

    products = []
    for i in range(size["products"]):
        category = rng.choice(list(CATEGORIES))
        cost = round(rng.uniform(5, 500), 2)
        products.append(
            {
                "src_row_id": i + 1,
                "product_id": _uuid(rng),
                "name": fake.catch_phrase(),
                "category": category,
                "subcategory": rng.choice(CATEGORIES[category]),
                "cost_price": f"{cost:.2f}",
                "list_price": f"{round(cost * rng.uniform(1.2, 2.5), 2):.2f}",
            }
        )

    usable_customers = [c["customer_id"] for c in customers[RESERVED_CUSTOMERS:]]
    usable_products = products[RESERVED_PRODUCTS:]

    orders = []
    for i in range(size["orders"]):
        created = _timestamp(rng, now, 90)
        updated = min(created + timedelta(hours=rng.randint(0, 240)), now)
        guest = rng.random() < 0.01  # a guest checkout has no customer, by design
        orders.append(
            {
                "src_row_id": i + 1,
                "order_id": _uuid(rng),
                "customer_id": "" if guest else rng.choice(usable_customers),
                "status": rng.choice(STATUSES),
                "channel": rng.choice(["web", "mobile_app", "store", "affiliate"]),
                "created_at": created.isoformat(timespec="seconds"),
                "updated_at": updated.isoformat(timespec="seconds"),
            }
        )

    items = []
    for order in orders:
        for _ in range(rng.randint(1, 5)):
            product = rng.choice(usable_products)
            price = float(product["list_price"])
            discount = round(price * rng.uniform(0, 0.3), 2) if rng.random() < 0.15 else 0.0
            items.append(
                {
                    "src_row_id": len(items) + 1,
                    "order_item_id": _uuid(rng),
                    "order_id": order["order_id"],
                    "product_id": product["product_id"],
                    "quantity": str(rng.randint(1, 10)),
                    "unit_price": f"{price:.2f}",
                    "discount_amount": f"{discount:.2f}",
                }
            )

    return {"customers": customers, "products": products, "orders": orders, "order_items": items}


def plant_defects(data: dict[str, list[dict]], seed: int, now: datetime) -> dict[str, list[int]]:
    """Change rows in place and return {rule_id: [src_row_id, ...]} as ground truth."""
    rng = random.Random(seed + 1)
    truth: dict[str, list[int]] = {}

    def record(rule: str, rows: list[dict]) -> None:
        truth.setdefault(rule, []).extend(int(r["src_row_id"]) for r in rows)

    def take(pool: list[dict], n: int) -> list[dict]:
        """Remove and return n rows, so each row carries exactly one planted defect."""
        chosen = rng.sample(pool, n)
        for row in chosen:
            pool.remove(row)
        return chosen

    # Customers: only the reserved rows, which no order refers to.
    reserved = list(data["customers"][:RESERVED_CUSTOMERS])
    for row in take(reserved, 6):
        row["customer_id"] = ""
        record("CUST_ID_NOT_NULL", [row])
    for row in take(reserved, 5):
        partner = take(reserved, 1)[0]
        row["customer_id"] = partner["customer_id"]
        record("CUST_ID_UNIQUE", [row, partner])
    rest = data["customers"][RESERVED_CUSTOMERS:]
    for row in take(rest, 20):
        row["email"] = rng.choice(["no-at-sign.example.com", "user@", "@example.com", "two words@x.com"])
        record("CUST_EMAIL_FORMAT", [row])
    for row in take(rest, 10):
        row["country"] = "XX"
        record("CUST_COUNTRY_ACCEPTED", [row])
    for row in take(rest, 8):
        row["created_at"] = (now + timedelta(days=rng.randint(30, 400))).isoformat(timespec="seconds")
        record("CUST_CREATED_NOT_FUTURE", [row])

    # Products: reserved rows only for the key defect.
    reserved = list(data["products"][:RESERVED_PRODUCTS])
    for row in take(reserved, 3):
        partner = take(reserved, 1)[0]
        row["product_id"] = partner["product_id"]
        record("PROD_ID_UNIQUE", [row, partner])
    rest = data["products"][RESERVED_PRODUCTS:]
    for row in take(rest, 5):
        row["cost_price"] = "0.00"
        record("PROD_COST_POSITIVE", [row])
    for row in take(rest, 5):
        row["list_price"] = f"{float(row['cost_price']) * 0.5:.2f}"
        record("PROD_PRICE_GE_COST", [row])

    # Orders.
    pool = list(data["orders"])
    next_id = len(data["orders"]) + 1
    for row in take(pool, 10):
        copy = dict(row, src_row_id=next_id)
        next_id += 1
        data["orders"].append(copy)
        record("ORD_ID_UNIQUE", [row, copy])
    for row in take(pool, 8):
        row["customer_id"] = _uuid(rng)
        record("ORD_CUSTOMER_FK", [row])
    for row in take(pool, 6):
        row["status"] = "archived"
        record("ORD_STATUS_ACCEPTED", [row])
    for row in take(pool, 7):
        created = datetime.fromisoformat(row["created_at"])
        row["updated_at"] = (created - timedelta(days=2)).isoformat(timespec="seconds")
        record("ORD_UPDATED_AFTER_CREATED", [row])
    for row in take(pool, 4):
        row["created_at"] = "31/02/2026 25:61"
        record("ORD_CREATED_PARSEABLE", [row])

    # Order items.
    pool = list(data["order_items"])
    for row in take(pool, 8):
        row["order_id"] = _uuid(rng)
        record("ITEM_ORDER_FK", [row])
    for row in take(pool, 5):
        row["product_id"] = _uuid(rng)
        record("ITEM_PRODUCT_FK", [row])
    for row in take(pool, 10):
        row["quantity"] = rng.choice(["0", "-2"])
        record("ITEM_QTY_POSITIVE", [row])
    for row in take(pool, 6):
        row["discount_amount"] = f"{float(row['unit_price']) + 5:.2f}"
        record("ITEM_DISCOUNT_LE_PRICE", [row])

    return {rule: sorted(ids) for rule, ids in truth.items()}


def write_files(data: dict[str, list[dict]], out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for entity, rows in data.items():
        pl.DataFrame(rows, infer_schema_length=None).write_csv(out / f"{entity}.csv")
        counts[entity] = len(rows)
    return counts


def upload_to_s3(out: Path, bucket: str, prefix: str = "raw") -> None:
    import boto3  # imported here so local runs do not need AWS libraries

    s3 = boto3.client("s3")
    for path in sorted(out.glob("*.csv")):
        key = f"{prefix}/{path.stem}/{path.name}"
        s3.upload_file(str(path), bucket, key)
        print(f"Uploaded s3://{bucket}/{key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["clean", "defects"], default="defects")
    parser.add_argument("--scale", choices=sorted(SCALES), default="small")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument("--s3-bucket", help="Also upload the files to this S3 bucket")
    args = parser.parse_args()

    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    data = generate_clean(args.seed, args.scale, now)
    truth = plant_defects(data, args.seed, now) if args.mode == "defects" else {}
    counts = write_files(data, args.out)
    (args.out / "defect_manifest.json").write_text(
        json.dumps({"mode": args.mode, "seed": args.seed, "rules": truth}, indent=2)
    )
    print(f"mode={args.mode} rows={counts} planted_rules={len(truth)}")
    if args.s3_bucket:
        upload_to_s3(args.out, args.s3_bucket)


if __name__ == "__main__":
    main()
