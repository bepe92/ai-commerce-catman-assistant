"""Agent 2 — Daily Deals Anomaly Detector.

Python calculates the percentage and assigns the hard-coded risk band
(>70% = HIGH, 50-70% = MEDIUM, 10-50% = LOW). The LLM contributes one
sentence of plain-language assessment per flagged deal — context the
trader can read at a glance ("looks like a misplaced decimal" vs
"plausible end-of-season clearance").
"""
from data_simulator import BazarekSnapshot
from llm_client import ask_json
from schemas import DealsAnomalyReport, DealAnomaly


# ──────────────────────────────────────────────────────────────
#  EDIT THIS PROMPT to change Agent 2's behaviour
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Jesteś agentem do oceny daily deals na platformie e-commerce Bazarek.

ZADANIE:
Otrzymasz listę ofert dziennych z procentem obniżki (Python już policzył). \
Dla każdej oferty napisz jednozdaniową ocenę po polsku: czy to wygląda jak \
legalna promocja, czy raczej błąd danych / błąd cenowy.

Wskazówki do interpretacji:
- Obniżka 10-50% to typowa promocja
- 50-70% to mocna wyprzedaż (koniec sezonu, stock clearance) — możliwa ale nietypowa
- >70% to zwykle błąd: pomyłka w cenach, pomylone wartości jednostkowe (np. zł vs eur), \
  źle przeniesione wartości z arkusza dostawcy

Zwróć WYŁĄCZNIE czysty JSON, bez znaczników ```:
{"assessments": [{"product_id": "...", "assessment": "jednozdaniowy opis po polsku"}, ...]}

NIE klasyfikuj risk_level — Python już to zrobił. Twoja rola to opis."""


async def run(snapshot: BazarekSnapshot) -> DealsAnomalyReport:
    # Python klasyfikuje ryzyko deterministycznie (matma to nie jest praca dla LLM).
    deals_above_threshold = []
    for d in snapshot.daily_deals:
        if d.discount_pct >= 10:
            risk = _risk_band(d.discount_pct)
            deals_above_threshold.append((d, risk))

    if not deals_above_threshold:
        return DealsAnomalyReport(summary="Brak daily deals do oceny.")

    # LLM tylko opisuje
    llm_input = [
        {"product_id": d.product_id, "product_name": d.product_name,
         "original_price": d.original_price, "deal_price": d.deal_price,
         "discount_pct": d.discount_pct, "currency": d.currency}
        for d, _ in deals_above_threshold
    ]
    llm_out = await ask_json(SYSTEM_PROMPT, {"deals": llm_input})
    assessments = {a["product_id"]: a["assessment"] for a in llm_out.get("assessments", [])}

    anomalies = [
        DealAnomaly(
            product_id=d.product_id, product_name=d.product_name,
            original_price=d.original_price, deal_price=d.deal_price,
            discount_pct=d.discount_pct, currency=d.currency,
            risk_level=risk,
            assessment=assessments.get(d.product_id, "(brak komentarza LLM)"),
        )
        for d, risk in deals_above_threshold
    ]

    high = sum(1 for a in anomalies if a.risk_level == "HIGH")
    med = sum(1 for a in anomalies if a.risk_level == "MEDIUM")
    summary = (f"Sprawdzono {len(anomalies)} promocji "
               f"(HIGH: {high}, MEDIUM: {med}). Promocje HIGH wymagają natychmiastowej weryfikacji cen.")
    return DealsAnomalyReport(summary=summary, anomalies=anomalies)


def _risk_band(pct: float) -> str:
    if pct > 70:
        return "HIGH"
    if pct >= 50:
        return "MEDIUM"
    return "LOW"
