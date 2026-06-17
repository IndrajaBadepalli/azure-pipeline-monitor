"""
Mock Customer API
Simulates a CRM / customer data platform.

Run with: uvicorn api_source.mock_customer_api:app --port 8001 --reload
"""

from fastapi import FastAPI, Query
from faker import Faker
from typing import Optional
import random
from datetime import datetime, timedelta

app  = FastAPI(title="Mock Customer API", version="1.0.0")
fake = Faker()
random.seed(99)

COUNTRIES   = ["Canada","USA","UK","Germany","France","Australia"]
SEGMENTS    = ["Premium","Standard","Basic"]
CHANNELS    = ["web","mobile","referral","organic","paid_search"]
EVENT_TYPES = ["login","product_view","support_ticket",
               "return_request","wishlist_add","newsletter_unsubscribe","app_open"]

def make_customers(n: int = 300, failure_type: str = None) -> list:
    customers = []
    for i in range(1, n + 1):
        signup_days  = random.randint(30, 1095)
        last_order   = random.randint(0, 365)
        total_orders = random.randint(1, 50)
        total_spend  = round(total_orders * random.uniform(30, 250), 2)

        email = fake.email()
        if failure_type == "null_spike" and random.random() < 0.15:
            email = None

        record = {
            "customer_id":           i,
            "full_name":             fake.name(),
            "email":                 email,
            "country":               random.choice(COUNTRIES),
            "city":                  fake.city(),
            "segment":               random.choice(SEGMENTS),
            "acquisition_channel":   random.choice(CHANNELS),
            "signup_date":           (datetime.utcnow() -
                                      timedelta(days=signup_days)).strftime("%Y-%m-%d"),
            "total_orders":          total_orders,
            "total_spend":           total_spend,
            "avg_order_value":       round(total_spend / total_orders, 2),
            "last_order_date":       (datetime.utcnow() -
                                      timedelta(days=last_order)).strftime("%Y-%m-%d"),
            "days_since_last_order": last_order,
            "is_email_verified":     random.choice([True, True, True, False]),
            "preferred_currency":    random.choice(["USD","CAD","GBP","EUR"]),
        }

        if failure_type == "schema_change":
            record["loyalty_tier"] = random.choice(["Gold","Silver","Bronze",None])

        customers.append(record)

    if failure_type == "volume_drop":
        return customers[:30]

    return customers

def make_events(n_customers: int = 300) -> list:
    events, event_id = [], 1
    for cid in range(1, n_customers + 1):
        for _ in range(random.randint(1, 5)):
            days_ago = random.randint(0, 90)
            events.append({
                "event_id":    event_id,
                "customer_id": cid,
                "event_type":  random.choice(EVENT_TYPES),
                "event_ts":    (datetime.utcnow() - timedelta(
                                   days=days_ago,
                                   hours=random.randint(0, 23)
                               )).isoformat(),
                "channel":     random.choice(CHANNELS),
            })
            event_id += 1
    return events

SEGMENT_RULES = [
    {"segment":"Premium",  "min_spend":1000, "min_orders":5},
    {"segment":"Standard", "min_spend":200,  "min_orders":2},
    {"segment":"Basic",    "min_spend":0,    "min_orders":1},
]

@app.get("/health")
def health():
    return {"status":"ok","timestamp":datetime.utcnow().isoformat()}

@app.get("/customers")
def get_customers(
    page:      int           = Query(1, ge=1),
    page_size: int           = Query(100, ge=1, le=500),
    failure:   Optional[str] = Query(None)
):
    all_customers = make_customers(300, failure_type=failure)
    start = (page - 1) * page_size
    end   = start + page_size
    return {
        "page":      page,
        "page_size": page_size,
        "total":     len(all_customers),
        "data":      all_customers[start:end]
    }

@app.get("/events")
def get_events(
    page:      int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000)
):
    all_events = make_events()
    start = (page - 1) * page_size
    end   = start + page_size
    return {
        "page":      page,
        "page_size": page_size,
        "total":     len(all_events),
        "data":      all_events[start:end]
    }

@app.get("/segments")
def get_segments():
    return {"total": len(SEGMENT_RULES), "data": SEGMENT_RULES}