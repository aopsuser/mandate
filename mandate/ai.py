"""Planner: turn a natural-language goal into a structured shopping plan.

Two modes, same contract:

* ``llm``       — an OpenAI-compatible chat endpoint plans the search.
* ``heuristic`` — a small rule-based planner, used when no key is set.

The heuristic fallback exists so the project runs end-to-end with zero
configuration. It is deliberately transparent rather than clever.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from . import catalog
from .config import Settings

CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "footwear": (
        "shoe", "shoes", "sneaker", "sneakers", "running", "trainer", "trainers",
        "footwear", "boot", "boots", "sandal", "sandals",
    ),
    "wearables": ("watch", "tracker", "wearable", "smartwatch"),
    "accessories": ("sock", "socks", "bottle", "accessory", "accessories", "hydration"),
}

STOPWORDS = {
    "find", "get", "me", "the", "best", "cheapest", "a", "an", "for", "under",
    "below", "less", "than", "budget", "of", "is", "up", "to", "max", "maximum",
    "please", "buy", "purchase", "some", "any", "with", "and", "from", "store",
    "shop", "pair", "pairs", "good", "great", "nice", "cheap", "lowest", "price",
}

STRATEGY_CHEAPEST = ("cheapest", "cheap", "lowest", "budget", "least expensive")
STRATEGY_BEST = ("best", "top", "highest rated", "highest-rated", "greatest")


def _extract_max_price(goal: str) -> float | None:
    patterns = [
        r"(?:under|below|less than|max(?:imum)?|up to|budget(?: of| is)?)\s*\$?\s*(\d+(?:\.\d+)?)",
        r"\$\s*(\d+(?:\.\d+)?)\s*(?:or less|max)",
    ]
    for pattern in patterns:
        match = re.search(pattern, goal, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _extract_keywords(goal: str) -> list[str]:
    lowered = goal.lower()
    keywords: list[str] = []

    # If the goal names a catalog product, that name is the strongest signal.
    for item in catalog.CATALOG:
        name = item["name"].lower()
        if name in lowered and name not in keywords:
            keywords.append(name)

    # Otherwise fall back to meaningful tokens that actually appear in the catalog.
    vocabulary: set[str] = set()
    for item in catalog.CATALOG:
        vocabulary.update(item["tags"])
        vocabulary.update(re.findall(r"[a-z0-9]+", item["name"].lower()))

    for token in re.findall(r"[a-z0-9]+", lowered):
        if len(token) < 3 or token in STOPWORDS or token.isdigit():
            continue
        if token in vocabulary and token not in keywords:
            keywords.append(token)

    return keywords[:4]


def _heuristic(goal: str) -> dict[str, Any]:
    lowered = goal.lower()
    category = None
    for name, hints in CATEGORY_HINTS.items():
        if any(hint in lowered for hint in hints):
            category = name
            break

    strategy = "balanced"
    if any(word in lowered for word in STRATEGY_CHEAPEST):
        strategy = "cheapest"
    elif any(word in lowered for word in STRATEGY_BEST):
        strategy = "best"

    keywords = _extract_keywords(goal)
    max_price = _extract_max_price(goal)

    bits = []
    bits.append(f"Interpreted the goal as a {category or 'general'} search")
    if keywords:
        bits.append(f"matching {', '.join(keywords)}")
    if max_price is not None:
        bits.append(f"capped at ${max_price:,.2f}")
    bits.append(f"ranked by {strategy} value")
    rationale = "; ".join(bits) + "."

    return {
        "strategy": strategy,
        "category": category,
        "max_price": max_price,
        "keywords": keywords,
        "rationale": rationale,
        "source": "heuristic",
    }


def _llm_plan(goal: str, settings: Settings) -> dict[str, Any] | None:
    catalog_summary = [
        {
            "name": item["name"],
            "merchant": item["merchant"],
            "category": item["category"],
            "price": item["price"],
            "tags": item["tags"],
        }
        for item in catalog.CATALOG
    ]

    system = (
        "You are the planning module of an autonomous shopping agent. "
        "Convert the user's goal into a search plan. Respond with JSON only, "
        "using exactly these keys: strategy ('cheapest' | 'best' | 'balanced'), "
        "category (one of footwear|wearables|accessories|null), "
        "max_price (number or null), keywords (array of short lowercase strings), "
        "rationale (one short sentence explaining the plan)."
    )
    user = json.dumps(
        {
            "goal": goal,
            "catalog": catalog_summary,
            "categories": catalog.CATEGORIES,
        },
        separators=(",", ":"),
    )

    request = urllib.request.Request(
        f"{settings.llm_base_url}/chat/completions",
        data=json.dumps(
            {
                "model": settings.llm_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))

    content = payload["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("model did not return JSON")
    plan = json.loads(content[start : end + 1])

    return {
        "strategy": plan.get("strategy") if plan.get("strategy") in {"cheapest", "best", "balanced"} else "balanced",
        "category": plan.get("category") if plan.get("category") in catalog.CATEGORIES else None,
        "max_price": float(plan["max_price"]) if plan.get("max_price") not in (None, "", "null") else None,
        "keywords": [str(k).lower() for k in (plan.get("keywords") or [])][:4],
        "rationale": str(plan.get("rationale") or "Model-planned search."),
        "source": "llm",
    }


def plan_goal(goal: str, settings: Settings) -> dict[str, Any]:
    if settings.llm_api_key:
        try:
            plan = _llm_plan(goal, settings)
            if plan is not None:
                return plan
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError):
            # Any model failure degrades gracefully to the deterministic planner.
            pass
    return _heuristic(goal)
