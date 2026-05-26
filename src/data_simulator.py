"""Generate a consistent fictional dataset for the Bazarek e-commerce platform.

The same product IDs flow through all five agents — when Agent 1 flags
offer-NPX12-001 as suspicious, Agent 5 might also see NPX12-001 with a click
spike. This consistency is what makes the multi-agent demo feel like a real
operations system rather than five disconnected toys.

Deterministic by date: same target_date produces the same dataset, so reruns
and screenshots are stable.

We deliberately embed obvious anomalies so each agent has something to flag:
  - At least one offer with a mismatched name (Agent 1)
  - At least one daily deal with >70% discount (Agent 2)
  - At least one product with >40% day-over-day sales swing (Agent 3)
  - One upcoming Nordic event within 14 days (Agent 4)
  - At least one product with a click spike (Agent 5)
"""
import random
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Any


# ===== Domain types =====
@dataclass
class Product:
    id: str
    name: str
    category: str
    base_price: float
    currency: str
    country: str


@dataclass
class Offer:
    id: str
    product_id: str
    name: str
    price: float
    currency: str


@dataclass
class DailyDeal:
    product_id: str
    product_name: str
    original_price: float
    deal_price: float
    discount_pct: float
    currency: str


@dataclass
class ClickRecord:
    product_id: str
    product_name: str
    category: str
    clicks_today: int
    clicks_yesterday: int


@dataclass
class SalesRecord:
    product_id: str
    product_name: str
    category: str
    sold_today: int
    sold_yesterday: int
    avg_7day: float


@dataclass
class NordicEvent:
    name: str
    event_date: date
    countries: list[str]
    affected_categories: list[str]
    description: str


@dataclass
class BazarekSnapshot:
    """Everything every agent needs for a single day. Built once, shared by all."""
    target_date: date
    products: list[Product]
    offers: list[Offer]
    daily_deals: list[DailyDeal]
    clicks: list[ClickRecord]
    sales: list[SalesRecord]
    events: list[NordicEvent]


# ===== Hardcoded seed material =====
# Fictional product catalog — Nordic-themed brand names so nothing collides with real trademarks.
_CATALOG: list[tuple[str, str, str, float, str, str]] = [
    # (id, name, category, base_price, currency, country)
    ("NPX12P",   "Nordic Phone X12 Pro",          "Electronics", 8999.0,  "SEK", "SE"),
    ("NPX12",    "Nordic Phone X12",              "Electronics", 5999.0,  "SEK", "SE"),
    ("FJTAB10",  "Fjord Tab 10 Plus",             "Electronics", 4499.0,  "NOK", "NO"),
    ("AURBUDS", "AuroraBuds Wireless Pro",       "Electronics", 1799.0,  "SEK", "SE"),
    ("VIKLAP",   "Viking Laptop Ultra 15",        "Electronics", 14990.0, "NOK", "NO"),
    ("SAUNAFX",  "SaunaFlex Smart Heater",        "Home",        5490.0,  "SEK", "SE"),
    ("ICEPOT",   "IcePot Espresso Maker",         "Home",        1290.0,  "DKK", "DK"),
    ("NORDESK",  "NordDesk Standing Desk Pro",    "Home",        6990.0,  "DKK", "DK"),
    ("SKIBOOT",  "SkiBoot Elite 2026",            "Sport",       2499.0,  "NOK", "NO"),
    ("LAPBIKE",  "LapBike Carbon Road",           "Sport",       18990.0, "SEK", "SE"),
    ("SAUNATWL", "SaunaTowel Bamboo XL",          "Home",         299.0,  "SEK", "SE"),
    ("NORDFLEEC", "NordFleece Half-Zip",          "Sport",        899.0,  "DKK", "DK"),
]

# Fictional Nordic events. Real cultural anchors (Midsommar, 17 Mai) plus invented product launches.
_EVENT_TEMPLATES: list[tuple[str, tuple[int, int], list[str], list[str], str]] = [
    # (name, (month, day), countries, affected_categories, description)
    ("Midsommar",                       (6, 21),  ["SE", "FI"],            ["Home", "Sport"],         "Peak summer holiday — outdoor and homeware demand spikes."),
    ("Norwegian Constitution Day (17 Mai)", (5, 17),  ["NO"],                  ["Home"],                  "National celebration — household and traditional-wear sales surge."),
    ("Singles' Day SE",                 (11, 11), ["SE", "NO", "DK", "FI"],["Electronics", "Home"],   "Imported retail event; expect 200-400% click volume on electronics."),
    ("Black Friday SE",                 (11, 28), ["SE", "FI"],            ["Electronics", "Sport"],  "Largest discount event of the year."),
    ("Black Friday NO/DK",              (11, 29), ["NO", "DK"],            ["Electronics", "Sport"],  "Norway and Denmark observe BF a day later than SE."),
    ("Nordic Phone X13 Launch",         (6,  5),  ["SE", "NO", "DK", "FI"],["Electronics"],           "Fictional flagship phone launch — premium electronics traffic spike."),
    ("Sankthansaften (St. John's Eve)", (6, 23),  ["NO", "DK"],            ["Home", "Sport"],         "Bonfire night — outdoor and grilling categories peak."),
    ("Lucia Day",                       (12, 13), ["SE"],                  ["Home"],                  "Candle, decoration, baking categories surge in the week prior."),
]


# ===== Builder =====
def build_snapshot(target_date: date | None = None, seed_override: int | None = None) -> BazarekSnapshot:
    """Build a deterministic dataset for the given date. Embeds anomalies on purpose."""
    target_date = target_date or date.today()
    seed = seed_override if seed_override is not None else _date_seed(target_date)
    rng = random.Random(seed)

    products = [
        Product(id=pid, name=name, category=cat, base_price=price, currency=cur, country=ctry)
        for pid, name, cat, price, cur, ctry in _CATALOG
    ]

    offers = _build_offers(products, rng)
    daily_deals = _build_daily_deals(products, rng)
    clicks = _build_clicks(products, rng)
    sales = _build_sales(products, rng)
    events = _build_events(target_date)

    return BazarekSnapshot(
        target_date=target_date,
        products=products,
        offers=offers,
        daily_deals=daily_deals,
        clicks=clicks,
        sales=sales,
        events=events,
    )


def _date_seed(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _build_offers(products: list[Product], rng: random.Random) -> list[Offer]:
    offers: list[Offer] = []
    for p in products:
        # 1-3 normal accessory offers per product, priced sensibly
        for i in range(1, rng.randint(2, 4)):
            offers.append(Offer(
                id=f"OFF-{p.id}-{i:02d}",
                product_id=p.id,
                name=p.name,
                price=round(p.base_price * rng.uniform(0.97, 1.03), 2),
                currency=p.currency,
            ))

    # ===== ANOMALY for Agent 1 — phone case offer indexed under flagship phone =====
    # Drags the reference price of the NPX12 Pro from 8999 SEK down to 299 SEK.
    offers.append(Offer(
        id="OFF-NPX12P-XX",
        product_id="NPX12P",
        name="Leather Case for Nordic Phone X12",   # accessory, wrong product
        price=299.0,
        currency="SEK",
    ))

    # ===== ANOMALY for Agent 1 — laptop sleeve mis-indexed under laptop =====
    offers.append(Offer(
        id="OFF-VIKLAP-XX",
        product_id="VIKLAP",
        name="Viking Laptop Sleeve 15\" (neoprene)",
        price=199.0,
        currency="NOK",
    ))

    return offers


def _build_daily_deals(products: list[Product], rng: random.Random) -> list[DailyDeal]:
    deals: list[DailyDeal] = []
    for p in products:
        # Half the catalog gets a legitimate discount each day
        if rng.random() < 0.5:
            discount = rng.uniform(0.10, 0.35)   # 10-35% normal promo
            deal_price = round(p.base_price * (1 - discount), 2)
            deals.append(DailyDeal(
                product_id=p.id, product_name=p.name,
                original_price=p.base_price, deal_price=deal_price,
                discount_pct=round(discount * 100, 1),
                currency=p.currency,
            ))

    # ===== ANOMALY for Agent 2 — absurd 85% discount, almost certainly a data error =====
    deals.append(DailyDeal(
        product_id="LAPBIKE", product_name="LapBike Carbon Road",
        original_price=18990.0, deal_price=2849.0,
        discount_pct=85.0,
        currency="SEK",
    ))

    # ===== ANOMALY for Agent 2 — 72% discount, suspicious but plausible =====
    deals.append(DailyDeal(
        product_id="AURBUDS", product_name="AuroraBuds Wireless Pro",
        original_price=1799.0, deal_price=499.0,
        discount_pct=72.3,
        currency="SEK",
    ))

    return deals


def _build_clicks(products: list[Product], rng: random.Random) -> list[ClickRecord]:
    records: list[ClickRecord] = []
    for p in products:
        baseline = rng.randint(200, 1200)
        records.append(ClickRecord(
            product_id=p.id, product_name=p.name, category=p.category,
            clicks_today=int(baseline * rng.uniform(0.85, 1.15)),
            clicks_yesterday=baseline,
        ))

    # ===== ANOMALY for Agent 5 — viral spike on a phone (200% jump) =====
    for r in records:
        if r.product_id == "NPX12P":
            r.clicks_today = int(r.clicks_yesterday * 3.2)
            break

    # ===== ANOMALY for Agent 5 — flat product suddenly dominant in its category =====
    # SaunaFlex normally moderate, today 5x competition
    for r in records:
        if r.product_id == "SAUNAFX":
            r.clicks_today = 4800
            break

    return records


def _build_sales(products: list[Product], rng: random.Random) -> list[SalesRecord]:
    records: list[SalesRecord] = []
    for p in products:
        baseline = rng.randint(8, 60)
        records.append(SalesRecord(
            product_id=p.id, product_name=p.name, category=p.category,
            sold_today=int(baseline * rng.uniform(0.9, 1.1)),
            sold_yesterday=baseline,
            avg_7day=round(baseline * rng.uniform(0.92, 1.08), 1),
        ))

    # ===== ANOMALY for Agent 3 — sales collapse, no event explanation =====
    for r in records:
        if r.product_id == "ICEPOT":
            r.sold_today = max(1, int(r.avg_7day * 0.45))   # ~55% drop
            break

    # ===== ANOMALY for Agent 3 — sales surge, no event explanation =====
    for r in records:
        if r.product_id == "AURBUDS":
            r.sold_today = int(r.avg_7day * 1.85)            # +85%
            break

    return records


def _build_events(target_date: date) -> list[NordicEvent]:
    """Materialise the static event templates into concrete dates within +/- 60 days."""
    out: list[NordicEvent] = []
    for name, (m, d), countries, cats, desc in _EVENT_TEMPLATES:
        # Try the current year first, then next year if it's already passed
        for year_offset in (0, 1):
            try:
                ed = date(target_date.year + year_offset, m, d)
            except ValueError:
                continue
            delta = (ed - target_date).days
            if -7 <= delta <= 60:
                out.append(NordicEvent(
                    name=name, event_date=ed, countries=countries,
                    affected_categories=cats, description=desc,
                ))
                break
    return sorted(out, key=lambda e: e.event_date)


def snapshot_to_dict(snapshot: BazarekSnapshot) -> dict[str, Any]:
    """Helper for orchestrator/report — JSON-friendly view of the full dataset."""
    return {
        "target_date": snapshot.target_date.isoformat(),
        "products": [asdict(p) for p in snapshot.products],
        "offers": [asdict(o) for o in snapshot.offers],
        "daily_deals": [asdict(d) for d in snapshot.daily_deals],
        "clicks": [asdict(c) for c in snapshot.clicks],
        "sales": [asdict(s) for s in snapshot.sales],
        "events": [{**asdict(e), "event_date": e.event_date.isoformat()} for e in snapshot.events],
    }
