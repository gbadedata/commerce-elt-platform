import polars as pl
from faker import Faker
import random
import uuid
import datetime
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

fake = Faker()
random.seed(42)

BATCH_ID = os.getenv("BATCH_ID", "batch_001")
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREFIX = os.getenv("S3_PREFIX", "raw")
DATE_PREFIX = datetime.date.today().strftime("year=%Y/month=%m/day=%d")

# ── Helpers ────────────────────────────────────────────────────────────────

def s3_key(entity: str, filename: str) -> str:
    return f"{S3_PREFIX}/{entity}/{DATE_PREFIX}/{filename}"


def upload_to_s3(df: pl.DataFrame, entity: str):
    filename = f"{BATCH_ID}_{entity}.csv"
    key = s3_key(entity, filename)
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=df.write_csv(),
        ContentType="text/csv",
    )
    print(f"  Uploaded {len(df):,} rows  →  s3://{S3_BUCKET}/{key}")


# ── Generators ─────────────────────────────────────────────────────────────

def generate_customers(n: int = 10_000) -> pl.DataFrame:
    rows = []
    for _ in range(n):
        # Deliberate DQ issue: 0.3% null customer_id
        cid = None if random.random() < 0.003 else str(uuid.uuid4())
        rows.append({
            "customer_id": cid,
            "email": fake.email().lower(),
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "country": random.choice(["NG", "GH", "KE", "ZA", "GB", "US"]),
            "acquisition_source": random.choice(
                ["organic", "paid_search", "social", "referral", "email", "direct"]
            ),
            "created_at": fake.date_time_between("-365d", "now").isoformat(),
            "updated_at": fake.date_time_between("-30d", "now").isoformat(),
        })
    return pl.DataFrame(rows)


def generate_products(n: int = 500) -> pl.DataFrame:
    categories = {
        "Electronics": ["Phones", "Laptops", "Tablets", "Accessories"],
        "Clothing":    ["Shirts", "Trainers", "Dresses", "Outerwear"],
        "Home":        ["Furniture", "Kitchen", "Bedding", "Lighting"],
        "Beauty":      ["Skincare", "Haircare", "Fragrance", "Makeup"],
        "Sports":      ["Gym", "Outdoors", "Cycling", "Swimming"],
    }
    rows = []
    for _ in range(n):
        category = random.choice(list(categories.keys()))
        subcategory = random.choice(categories[category])
        cost = round(random.uniform(5, 500), 2)
        # Deliberate DQ issue: 2% have cost_price = 0
        if random.random() < 0.02:
            cost = 0.0
        list_price = round(cost * random.uniform(1.2, 2.5), 2)
        rows.append({
            "product_id":   str(uuid.uuid4()),
            "name":         fake.catch_phrase(),
            "category":     category,
            "subcategory":  subcategory,
            "cost_price":   cost,
            "list_price":   list_price,
            "is_active":    True,
            "created_at":   fake.date_time_between("-365d", "now").isoformat(),
        })
    return pl.DataFrame(rows)


def generate_orders(customers: pl.DataFrame, n: int = 50_000) -> pl.DataFrame:
    valid_customers = customers.filter(
        pl.col("customer_id").is_not_null()
    )["customer_id"].to_list()

    statuses = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
    channels = ["web", "mobile_app", "store", "affiliate"]
    countries = ["NG", "GH", "KE", "ZA", "GB", "US"]

    rows = []
    for _ in range(n):
        # Deliberate DQ issue: 0.1% duplicate order_ids (added at end)
        oid = str(uuid.uuid4())
        # 1% guest checkouts — null customer_id
        cid = None if random.random() < 0.01 else random.choice(valid_customers)
        created = fake.date_time_between("-90d", "now")
        rows.append({
            "order_id":         oid,
            "customer_id":      cid,
            "status":           random.choice(statuses),
            "channel":          random.choice(channels),
            "shipping_country": random.choice(countries),
            "shipping_city":    fake.city(),
            "promo_code":       fake.bothify("SAVE##") if random.random() < 0.2 else None,
            "created_at":       created.isoformat(),
            "updated_at":       fake.date_time_between(created, "now").isoformat(),
        })

    df = pl.DataFrame(rows)

    # Inject ~0.1% duplicate order_ids
    n_dupes = max(1, int(n * 0.001))
    dupes = df.sample(n_dupes)
    df = pl.concat([df, dupes])

    return df


def generate_order_items(
    orders: pl.DataFrame, products: pl.DataFrame
) -> pl.DataFrame:
    order_ids  = orders["order_id"].to_list()
    product_ids = products["product_id"].to_list()
    prices     = dict(zip(
        products["product_id"].to_list(),
        products["list_price"].to_list()
    ))

    rows = []
    for oid in order_ids:
        n_items = random.randint(1, 5)
        for _ in range(n_items):
            pid = random.choice(product_ids)
            qty = random.randint(1, 10)
            # Deliberate DQ issue: 0.2% have quantity = 0
            if random.random() < 0.002:
                qty = 0
            unit_price = prices[pid]
            discount   = round(unit_price * random.uniform(0, 0.3), 2) \
                         if random.random() < 0.15 else 0.0
            rows.append({
                "order_item_id":  str(uuid.uuid4()),
                "order_id":       oid,
                "product_id":     pid,
                "quantity":       qty,
                "unit_price":     unit_price,
                "discount_amount": discount,
            })
    return pl.DataFrame(rows)


def generate_events(customers: pl.DataFrame, n: int = 200_000) -> pl.DataFrame:
    valid_customers = customers.filter(
        pl.col("customer_id").is_not_null()
    )["customer_id"].to_list()

    event_types = [
        "page_view", "search", "add_to_cart",
        "remove_from_cart", "purchase", "login", "logout"
    ]
    rows = []
    for _ in range(n):
        cid = None if random.random() < 0.3 else random.choice(valid_customers)
        etype = random.choice(event_types)
        rows.append({
            "event_id":   str(uuid.uuid4()),
            "customer_id": cid,
            "session_id": str(uuid.uuid4()),
            "event_type": etype,
            "page_url":   fake.uri() if etype in ("page_view", "search") else None,
            "product_id": None,
            "created_at": fake.date_time_between("-90d", "now").isoformat(),
        })
    return pl.DataFrame(rows)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Commerce ELT — Data Generator")
    print(f"  Batch : {BATCH_ID}")
    print(f"  Bucket: {S3_BUCKET}")
    print(f"{'='*55}\n")

    print("Generating customers...")
    customers = generate_customers(10_000)
    print(f"  {len(customers):,} rows  |  null IDs: "
          f"{customers['customer_id'].null_count()}")

    print("Generating products...")
    products = generate_products(500)

    print("Generating orders...")
    orders = generate_orders(customers, 50_000)
    print(f"  {len(orders):,} rows (includes deliberate duplicates)")

    print("Generating order items...")
    items = generate_order_items(orders, products)
    print(f"  {len(items):,} rows")

    print("Generating events...")
    events = generate_events(customers, 200_000)

    print("\nUploading to S3...")
    for entity, df in [
        ("customers",   customers),
        ("products",    products),
        ("orders",      orders),
        ("order_items", items),
        ("events",      events),
    ]:
        upload_to_s3(df, entity)

    print(f"\n✓ All entities uploaded for {BATCH_ID}\n")


if __name__ == "__main__":
    main()