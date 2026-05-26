"""Agent 3 — Sales Data Anomaly Detector.

Python computes the percentage swing vs the 7-day average and flags everything
above the 40% threshold (positive or negative). The LLM then receives the
flagged items plus the calendar of nearby Nordic events and writes a
one-sentence cause hypothesis per product: data error, supply issue, viral
effect, organic seasonal demand, etc.
"""
from data_simulator import BazarekSnapshot
from llm_client import ask_json
from schemas import SalesAnomalyReport, SalesAnomaly

THRESHOLD_PCT = 40.0


# ──────────────────────────────────────────────────────────────
#  EDIT THIS PROMPT to change Agent 3's behaviour
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Jesteś agentem analizy sprzedaży na platformie e-commerce Bazarek (rynki nordyckie).

ZADANIE:
Otrzymasz listę produktów których dzisiejsza sprzedaż odbiega o >40% od średniej 7-dniowej. \
Otrzymasz też listę nadchodzących eventów nordyckich. Dla każdego flagowanego produktu \
zaproponuj najbardziej prawdopodobną przyczynę.

Wskazówki:
- Spadek sprzedaży bez eventu → możliwy błąd danych (brak indeksowania), problem z dostępnością, błąd cenowy
- Wzrost sprzedaży bez eventu → efekt viralowy, ekspozycja w mediach, błąd cenowy w drugą stronę (za niska cena)
- Wzrost przed eventem (event w ciągu 7-14 dni dla kategorii produktu) → naturalny ruch sezonowy
- Spadek po eventcie → cooling-off, normalny powrót do bazowej

DLA KAŻDEGO produktu zwróć jeden obiekt:
{"product_id": "...", "likely_cause": "jednozdaniowa hipoteza po polsku"}

Zwróć WYŁĄCZNIE czysty JSON:
{"causes": [{...}, {...}]}"""


async def run(snapshot: BazarekSnapshot) -> SalesAnomalyReport:
    flagged = []
    for s in snapshot.sales:
        if s.avg_7day <= 0:
            continue
        pct_vs_avg = ((s.sold_today - s.avg_7day) / s.avg_7day) * 100
        if abs(pct_vs_avg) >= THRESHOLD_PCT:
            severity = "HIGH" if abs(pct_vs_avg) >= 60 else "MEDIUM"
            flagged.append((s, pct_vs_avg, severity))

    if not flagged:
        return SalesAnomalyReport(summary="Sprzedaż w normie — żaden produkt nie odbiega >40% od średniej 7-dniowej.")

    llm_input = {
        "flagged_products": [
            {
                "product_id": s.product_id, "product_name": s.product_name, "category": s.category,
                "sold_today": s.sold_today, "sold_yesterday": s.sold_yesterday,
                "avg_7day": s.avg_7day, "pct_vs_avg": round(pct, 1),
            }
            for s, pct, _ in flagged
        ],
        "upcoming_events": [
            {"name": e.name, "event_date": e.event_date.isoformat(),
             "affected_categories": e.affected_categories}
            for e in snapshot.events[:5]
        ],
    }

    llm_out = await ask_json(SYSTEM_PROMPT, llm_input)
    causes = {c["product_id"]: c["likely_cause"] for c in llm_out.get("causes", [])}

    anomalies = [
        SalesAnomaly(
            product_id=s.product_id, product_name=s.product_name, category=s.category,
            sold_today=s.sold_today, sold_yesterday=s.sold_yesterday,
            avg_7day=s.avg_7day, pct_vs_avg=round(pct, 1),
            severity=severity,
            likely_cause=causes.get(s.product_id, "(brak hipotezy LLM)"),
        )
        for s, pct, severity in flagged
    ]

    high = sum(1 for a in anomalies if a.severity == "HIGH")
    summary = (f"Wykryto {len(anomalies)} produktów z nietypową sprzedażą (HIGH: {high}). "
               f"Każdy ma hipotezę przyczyny od LLM-a opartą o kalendarz eventów.")
    return SalesAnomalyReport(summary=summary, anomalies=anomalies)
