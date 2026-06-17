"""
Mock Orders API
Simulates a real e-commerce orders system.

Run with: uvicorn api_source.mock_orders_api:app --port 8000 --reload
"""

from fastapi import FastAPI, Query
from faker import Faker
from typing import Optional
import random
from datetime import datetime, timedelta

app  = FastAPI(title="Mock Orders API", version="1.0.0")
fake = Faker()
random.seed(42)

# Fixed product catalog
PRODUCTS = [
    {
        "product_id": i,
        "product_name": fake.catch_phrase(),
        "category": random.choice(["Electronics","Clothing","Books","Home","Sports"]),
        "price": round(random.uniform(10, 500), 2)
    }
    for i in range(1, 51)
]

def make_orders(n: int = 100, failure_type: str = None) -> list:
    orders = []
    for i in range(1, n + 1):
        amount     = round(random.uniform(10, 1000), 2)
        order_time = datetime.utcnow() - timedelta(hours=random.randint(0, 4))

        if failure_type == "null_spike" and random.random() < 0.15:
            amount = None

        if failure_type == "late_data":
            order_time = datetime.utcnow() - timedelta(hours=random.randint(10, 24))

        orders.append({
            "order_id":        i,
            "customer_id":     random.randint(1, 300),
            "product_id":      random.randint(1, 50),
            "order_timestamp": order_time.isoformat(),
            "status":          random.choice(["completed","pending","cancelled"]),
            "amount":          amount,
            "currency":        random.choice(["USD","CAD","GBP","EUR"]),
            "source_channel":  random.choice(["web","mobile","api"]),
        })

    if failure_type == "volume_drop":
        return orders[:10]

    return orders

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/orders")
def get_orders(
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(100, ge=1, le=500),
    failure:   Optional[str] = Query(None)
):
    all_orders = make_orders(100, failure_type=failure)
    start = (page - 1) * page_size
    end   = start + page_size
    return {
        "page":      page,
        "page_size": page_size,
        "total":     len(all_orders),
        "data":      all_orders[start:end]
    }

@app.get("/products")
def get_products():
    return {"total": len(PRODUCTS), "data": PRODUCTS}
