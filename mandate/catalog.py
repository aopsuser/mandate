"""A tiny mock storefront so the agent has something to shop.

Prices and merchants are deliberately arranged to exercise every policy
rail: one product is listed cheaper on a marketplace that is not on the
allowlist, one sits above the approval threshold, and one is in the wrong
category entirely.
"""

from __future__ import annotations

from typing import Any

CATALOG: list[dict[str, Any]] = [
    {
        "id": "sku_tempo_market",
        "name": "Aero Tempo 4",
        "merchant": "sneakerhub.market",
        "merchant_name": "SneakerHub Marketplace",
        "category": "footwear",
        "price": 109.00,
        "rating": 4.6,
        "tags": ["running", "road", "tempo", "lightweight", "neutral"],
        "seller_type": "marketplace",
    },
    {
        "id": "sku_tempo_stride",
        "name": "Aero Tempo 4",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "footwear",
        "price": 118.00,
        "rating": 4.6,
        "tags": ["running", "road", "tempo", "lightweight", "neutral"],
        "seller_type": "official",
    },
    {
        "id": "sku_trail_stride",
        "name": "Trail Blaze 2",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "footwear",
        "price": 96.00,
        "rating": 4.4,
        "tags": ["trail", "running", "rugged", "grippy"],
        "seller_type": "official",
    },
    {
        "id": "sku_sprint_stride",
        "name": "Sprint Lite",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "footwear",
        "price": 74.00,
        "rating": 4.2,
        "tags": ["running", "lightweight", "budget", "daily"],
        "seller_type": "official",
    },
    {
        "id": "sku_cloud_runners",
        "name": "Cloudstride 5",
        "merchant": "runnersdepot.com",
        "merchant_name": "Runner's Depot",
        "category": "footwear",
        "price": 89.00,
        "rating": 4.5,
        "tags": ["running", "cushioned", "daily", "comfort"],
        "seller_type": "official",
    },
    {
        "id": "sku_velocity_runners",
        "name": "Velocity Pro",
        "merchant": "runnersdepot.com",
        "merchant_name": "Runner's Depot",
        "category": "footwear",
        "price": 132.00,
        "rating": 4.7,
        "tags": ["running", "racing", "carbon", "fast"],
        "seller_type": "official",
    },
    {
        "id": "sku_velocity_market",
        "name": "Velocity Pro",
        "merchant": "sneakerhub.market",
        "merchant_name": "SneakerHub Marketplace",
        "category": "footwear",
        "price": 121.00,
        "rating": 4.7,
        "tags": ["running", "racing", "carbon", "fast"],
        "seller_type": "marketplace",
    },
    {
        "id": "sku_daily_runners",
        "name": "Daily Trainer X",
        "merchant": "runnersdepot.com",
        "merchant_name": "Runner's Depot",
        "category": "footwear",
        "price": 64.00,
        "rating": 4.0,
        "tags": ["running", "training", "budget"],
        "seller_type": "official",
    },
    {
        "id": "sku_pulse_watch",
        "name": "Pulse Watch",
        "merchant": "gadgetstore.io",
        "merchant_name": "Gadget Store",
        "category": "wearables",
        "price": 99.00,
        "rating": 4.3,
        "tags": ["watch", "tracker", "heart-rate", "wearable"],
        "seller_type": "official",
    },
    {
        "id": "sku_hydra_bottle",
        "name": "Hydra Bottle",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "accessories",
        "price": 24.00,
        "rating": 4.1,
        "tags": ["bottle", "hydration", "accessory"],
        "seller_type": "official",
    },
    {
        "id": "sku_recovery_sandal",
        "name": "Recovery Sandal",
        "merchant": "runnersdepot.com",
        "merchant_name": "Runner's Depot",
        "category": "footwear",
        "price": 58.00,
        "rating": 4.2,
        "tags": ["recovery", "sandal", "post-run"],
        "seller_type": "official",
    },
    {
        "id": "sku_grip_socks",
        "name": "Grip Socks 3-pack",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "accessories",
        "price": 18.00,
        "rating": 4.0,
        "tags": ["socks", "accessory", "training"],
        "seller_type": "official",
    },
]

CATEGORIES = sorted({item["category"] for item in CATALOG})
MERCHANTS = sorted({item["merchant"] for item in CATALOG})


def get_item(item_id: str) -> dict[str, Any] | None:
    return next((item for item in CATALOG if item["id"] == item_id), None)


def search_catalog(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter + rank the catalog according to a planner plan."""
    category = plan.get("category")
    max_price = plan.get("max_price")
    keywords = [str(k).lower().strip() for k in (plan.get("keywords") or []) if str(k).strip()]
    strategy = plan.get("strategy") or "balanced"

    results: list[dict[str, Any]] = []
    for item in CATALOG:
        if category and item["category"] != category:
            continue
        if max_price is not None and item["price"] > float(max_price) + 1e-9:
            continue
        haystack = f"{item['name']} {' '.join(item['tags'])}".lower()
        if keywords and not any(k in haystack for k in keywords):
            continue
        results.append(item)

    if strategy == "cheapest":
        results.sort(key=lambda i: (i["price"], -i["rating"]))
    elif strategy == "best":
        results.sort(key=lambda i: (-i["rating"], i["price"]))
    else:
        # balanced: value = rating weighted against price
        results.sort(key=lambda i: (-(i["rating"] * 20 - i["price"] / 20), i["price"]))
    return results
