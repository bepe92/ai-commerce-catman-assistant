"""Agent 1 — Price Anomaly Detector.

Catches offers whose name does not match the parent product they sit under,
which drags down the product's reference price. Example: a "Leather Case for
Nordic Phone X12" offer indexed under the "Nordic Phone X12 Pro" product
pushes that product's reference price from 8999 SEK to 299 SEK.

Python does the filtering (which offers have prices wildly below product base);
the LLM does the semantic check ("does this offer name belong to this product?").
"""
from dataclasses import asdict
from data_simulator import BazarekSnapshot
from llm_client import ask_json
from schemas import PriceAnomalyReport, PriceAnomaly

# ──────────────────────────────────────────────────────────────
#  EDIT THIS PROMPT to change Agent 1's behaviour
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Jesteś agentem do wykrywania niezgodności ofert i produktów na platformie e-commerce Bazarek (rynki nordyckie).

ZADANIE:
Otrzymasz listę "kandydatów" — par {offer, product}. Każda para ma:
- nazwę oferty (offer.name)
- nazwę produktu pod który oferta jest podpięta (product.name)
- ceny obu

Dla każdej pary oceń, czy oferta semantycznie pasuje do produktu. \
Klasyczna anomalia: oferta akcesorium (np. "Leather Case for X") jest podpięta \
pod produkt główny (np. "Phone X Pro"), co psuje cenę referencyjną.

DLA KAŻDEJ pary zwróć obiekt z polami:
  - offer_id, offer_name, product_id, product_name (przepisz z inputu)
  - offer_price, product_base_price, currency (przepisz z inputu)
  - severity: "HIGH" jeśli oferta to wyraźnie akcesorium podpięte pod produkt główny, \
              "MEDIUM" jeśli niejasne dopasowanie, "LOW" jeśli pasuje.
  - reason: jednozdaniowe uzasadnienie po polsku

ZASADY:
- NIE wykonuj obliczeń. Tylko czytasz nazwy.
- Zwróć WYŁĄCZNIE czysty JSON, bez znaczników ```, bez komentarza.
- Format: {"results": [{...}, {...}, ...]}"""


async def run(snapshot: BazarekSnapshot) -> PriceAnomalyReport:
    products_by_id = {p.id: p for p in snapshot.products}

    # Python pre-filter: oferty o cenie znacząco niższej niż produkt bazowy są "kandydatami".
    # 50% poniżej ceny bazowej = jest co sprawdzać semantycznie.
    candidates = []
    for offer in snapshot.offers:
        product = products_by_id.get(offer.product_id)
        if product is None:
            continue
        if offer.price < product.base_price * 0.5:
            candidates.append({
                "offer_id": offer.id,
                "offer_name": offer.name,
                "product_id": product.id,
                "product_name": product.name,
                "offer_price": offer.price,
                "product_base_price": product.base_price,
                "currency": product.currency,
            })

    if not candidates:
        return PriceAnomalyReport(
            summary="Wszystkie oferty mają ceny w okolicach ceny bazowej produktu — brak kandydatów do analizy semantycznej.",
        )

    llm_result = await ask_json(SYSTEM_PROMPT, {"candidates": candidates})
    raw_results = llm_result.get("results", [])

    anomalies = [PriceAnomaly(**r) for r in raw_results if r.get("severity") in ("HIGH", "MEDIUM")]

    if not anomalies:
        summary = f"Sprawdzono {len(candidates)} podejrzanych ofert — wszystkie poprawnie dopasowane."
    else:
        high = sum(1 for a in anomalies if a.severity == "HIGH")
        summary = f"Wykryto {len(anomalies)} niezgodności (HIGH: {high}). Mogą zaniżać ceny referencyjne produktów głównych."

    return PriceAnomalyReport(summary=summary, anomalies=anomalies)
