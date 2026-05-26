"""Agent 4 — Nordic Event Manager.

Pure-Python event windowing (which events fall in the next 14 days?) feeds
the LLM, which then writes a category-specific preparation recommendation
per event. The LLM knows what categories the event affects, the LLM is
asked what ops should do this week to prepare.
"""
from data_simulator import BazarekSnapshot
from llm_client import ask_json
from schemas import EventManagerReport, UpcomingEvent

HORIZON_DAYS = 14


# ──────────────────────────────────────────────────────────────
#  EDIT THIS PROMPT to change Agent 4's behaviour
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Jesteś agentem przygotowania do eventów nordyckich na platformie e-commerce Bazarek.

ZADANIE:
Otrzymasz listę eventów (kulturalnych, sezonowych, premier produktów) zbliżających się \
w ciągu 14 dni dla rynków skandynawskich. Dla każdego eventu napisz konkretną \
rekomendację po polsku dla zespołu operacyjnego: co powinni przygotować w ciągu \
najbliższych dni, na które kategorie zwrócić uwagę.

ZASADY:
- Rekomendacja musi być KONKRETNA — np. "zwiększyć buforowy stock kategorii X o 30%" \
  zamiast "przygotować się"
- Klasyfikuj severity: "HIGH" jeśli event w ciągu 3 dni LUB to event masowy (Black Friday, Singles Day), \
  "MEDIUM" jeśli event w ciągu 4-10 dni, "INFO" jeśli powyżej 10 dni
- Zwróć WYŁĄCZNIE czysty JSON:
  {"recommendations": [{"name": "...", "severity": "HIGH|MEDIUM|INFO", "recommendation": "..."}, ...]}"""


async def run(snapshot: BazarekSnapshot) -> EventManagerReport:
    target = snapshot.target_date
    upcoming = []
    for e in snapshot.events:
        days_until = (e.event_date - target).days
        if 0 <= days_until <= HORIZON_DAYS:
            upcoming.append((e, days_until))

    if not upcoming:
        return EventManagerReport(summary=f"Brak eventów nordyckich w ciągu najbliższych {HORIZON_DAYS} dni.")

    llm_input = {
        "events": [
            {"name": e.name, "event_date": e.event_date.isoformat(),
             "days_until": d, "countries": e.countries,
             "affected_categories": e.affected_categories,
             "description": e.description}
            for e, d in upcoming
        ]
    }

    llm_out = await ask_json(SYSTEM_PROMPT, llm_input)
    recs = {r["name"]: r for r in llm_out.get("recommendations", [])}

    items = [
        UpcomingEvent(
            name=e.name, event_date=e.event_date.isoformat(), days_until=d,
            countries=e.countries, affected_categories=e.affected_categories,
            severity=recs.get(e.name, {}).get("severity", "INFO"),
            recommendation=recs.get(e.name, {}).get("recommendation", "(brak rekomendacji)"),
        )
        for e, d in upcoming
    ]

    high = sum(1 for i in items if i.severity == "HIGH")
    summary = (f"W ciągu {HORIZON_DAYS} dni: {len(items)} eventów (HIGH: {high}). "
               f"LLM przygotował konkretne rekomendacje per event.")
    return EventManagerReport(summary=summary, upcoming=items)
