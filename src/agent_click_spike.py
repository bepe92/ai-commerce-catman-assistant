"""Agent 5 — Click Spike Detector.

Two trigger conditions, both computed in Python:
  (a) clicks_today is at least 2x the #2 product in the same category, OR
  (b) clicks_today is up >150% vs clicks_yesterday for the same product.

The LLM then receives each flagged product plus its context (category leaderboard,
upcoming events affecting the category) and writes an interpretation: organic
signal (viral, launch, event tailwind) vs data anomaly worth verifying.
"""
from collections import defaultdict
from data_simulator import BazarekSnapshot
from llm_client import ask_json
from schemas import ClickSpikeReport, ClickSpike


# ──────────────────────────────────────────────────────────────
#  EDIT THIS PROMPT to change Agent 5's behaviour
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Jesteś agentem analizy ruchu (kliknięć) na platformie e-commerce Bazarek.

ZADANIE:
Otrzymasz listę produktów z anomaliami w kliknięciach — Python już je wykrył:
  (a) klikalność dziś jest 2x lub więcej wyższa niż #2 w kategorii, LUB
  (b) wzrost o >150% względem dnia poprzedniego.

Dla każdego produktu napisz jednozdaniową INTERPRETACJĘ po polsku:
  - "organic": realny ruch — viral, news media, premiera, event sezonowy
  - "data_anomaly": coś jest nie tak — błąd indeksowania, bot scraping, błąd cenowy \
    który przyciąga kliki

Otrzymasz też kalendarz nadchodzących eventów — wykorzystaj go (np. spike na elektronice \
przed Singles Day jest "organic"; spike na grzejnikach w środku lata bez eventu jest \
"data_anomaly").

KLASYFIKUJ severity:
- "HIGH": wzrost >300% bez wytłumaczenia eventem
- "MEDIUM": wzrost 150-300% lub dominacja kategorii bez eventu
- "LOW": wzrost znaczący ale wyjaśnialny eventem

Zwróć WYŁĄCZNIE czysty JSON:
{"interpretations": [{"product_id": "...", "severity": "...", "interpretation": "..."}, ...]}"""


async def run(snapshot: BazarekSnapshot) -> ClickSpikeReport:
    # ===== Python: kategoria → posortowane kliknięcia =====
    by_cat: dict[str, list] = defaultdict(list)
    for c in snapshot.clicks:
        by_cat[c.category].append(c)
    for lst in by_cat.values():
        lst.sort(key=lambda r: r.clicks_today, reverse=True)

    flagged = []
    for c in snapshot.clicks:
        # (a) dominacja w kategorii — #1 vs #2 ratio
        leaderboard = by_cat[c.category]
        dominance = 0.0
        if len(leaderboard) >= 2 and leaderboard[0].product_id == c.product_id:
            second = leaderboard[1].clicks_today
            if second > 0:
                dominance = c.clicks_today / second

        # (b) wzrost dzień-do-dnia
        if c.clicks_yesterday > 0:
            pct_change = ((c.clicks_today - c.clicks_yesterday) / c.clicks_yesterday) * 100
        else:
            pct_change = 0.0

        if dominance >= 2.0 or pct_change >= 150:
            flagged.append((c, pct_change, dominance))

    if not flagged:
        return ClickSpikeReport(summary="Brak anomalii w kliknięciach.")

    llm_input = {
        "flagged_products": [
            {
                "product_id": c.product_id, "product_name": c.product_name, "category": c.category,
                "clicks_today": c.clicks_today, "clicks_yesterday": c.clicks_yesterday,
                "pct_change": round(pct, 1), "dominance_in_category": round(dom, 2),
            }
            for c, pct, dom in flagged
        ],
        "upcoming_events": [
            {"name": e.name, "event_date": e.event_date.isoformat(),
             "affected_categories": e.affected_categories}
            for e in snapshot.events[:5]
        ],
    }

    llm_out = await ask_json(SYSTEM_PROMPT, llm_input)
    interp_by_id = {i["product_id"]: i for i in llm_out.get("interpretations", [])}

    spikes = [
        ClickSpike(
            product_id=c.product_id, product_name=c.product_name, category=c.category,
            clicks_today=c.clicks_today, clicks_yesterday=c.clicks_yesterday,
            pct_change=round(pct, 1), dominance_in_category=round(dom, 2),
            severity=interp_by_id.get(c.product_id, {}).get("severity", "MEDIUM"),
            interpretation=interp_by_id.get(c.product_id, {}).get("interpretation", "(brak interpretacji)"),
        )
        for c, pct, dom in flagged
    ]

    high = sum(1 for s in spikes if s.severity == "HIGH")
    summary = (f"Wykryto {len(spikes)} produktów z anomaliami klikowymi (HIGH: {high}). "
               f"LLM rozpoznaje czy to sygnał organiczny czy do weryfikacji danych.")
    return ClickSpikeReport(summary=summary, spikes=spikes)
