"""Orchestrator — fan-out 5 agents in parallel, fan-in their reports, compose HTML.

Key design:
  - Orchestrator does NOT know how any agent works. It calls .run(snapshot)
    on each and trusts the Pydantic-validated AgentReport it gets back.
  - All five agents run via asyncio.gather() so total wall-clock is roughly
    max(agent times), not sum. With ~1 LLM call per agent at ~2s each,
    sequential would be ~10s; parallel is ~2-3s.
  - If one agent fails, its exception is captured and surfaced in the
    aggregated result, but the other four still produce useful output.
  - Final HTML composition uses a more capable model (Sonnet) — same
    aggregated JSON, but the output is a polished management-ready report.
"""
import asyncio
import time
from datetime import date
from pathlib import Path

import agent_click_spike
import agent_deals_anomaly
import agent_event_manager
import agent_price_anomaly
import agent_sales_anomaly
from data_simulator import BazarekSnapshot, build_snapshot
from llm_client import ask_text
from schemas import (
    AgentReport,
    ClickSpikeReport,
    DealsAnomalyReport,
    EventManagerReport,
    OrchestratorResult,
    PriceAnomalyReport,
    SalesAnomalyReport,
)


REPORT_DIR = Path(__file__).parent.parent / "output"


# ──────────────────────────────────────────────────────────────
#  Fallback in-code prompt. Production-grade behaviour loads the
#  *editable* version from the sibling ai-prompt-manager repo so
#  category managers can iterate without code changes.
# ──────────────────────────────────────────────────────────────
_FALLBACK_REPORT_PROMPT = """Jesteś analitykiem operacyjnym dla category managerów platformy porównywarki/marketplace Bazarek \
(rynki nordyckie). Platforma trackuje konwersje (transakcje finalizowane przez użytkowników \
przekierowanych do partnerów), oferty partnerów, kliknięcia i ruch — NIE prowadzi sprzedaży własnej. \
Twoim zadaniem jest złożyć z surowych wyników 5 agentów AI jeden czytelny HTML-owy raport poranny \
dla category managera.

WYMAGANY UKŁAD RAPORTU (3 sekcje):

1. PILNE — wymaga działania DZIŚ. Wszystko o severity HIGH ze wszystkich agentów.
2. DO SPRAWDZENIA — anomalie niskiego/średniego ryzyka (MEDIUM, LOW).
3. INFORMACYJNE — nadchodzące eventy, trendy, kontekst.

ZASADY:
- Czysty prosty HTML, bez <html>/<head>/<body> — tylko fragment do wstawienia w template.
- Używaj klas CSS: section.urgent, section.review, section.info, table.deals, ul.recs.
- KAŻDY flagowany item musi mieć: nazwę produktu, kategorię, konkretną liczbę (kwota, %, etc.) \
  i jednozdaniowe wytłumaczenie. NIE pisz vague "produkt X ma anomalię" — pisz "LapBike Carbon Road \
  obniżony w ofercie o 85% (18 990 SEK → 2 849 SEK) — prawdopodobny błąd cenowy partnera".
- Ton: zwięzły, profesjonalny, "Bloomberg morning note" w domenie marketplace/comparison.
- TERMINOLOGIA: pisz o "konwersjach", "wolumenie konwersji", "ofertach partnerów", "kliknięciach", \
  "katalogu". NIE pisz "sprzedaż" / "sprzedaż własna" — Bazarek nie sprzedaje, tylko porównuje i \
  trackuje finalizację u partnerów.
- Język: polski.
- NIE wymyślaj liczb. Tylko to co dostałeś w danych.
- Każdy item miej w czytelnym formacie HTML (np. <div class="item">, <p>, <strong>).
- Jeśli sekcja jest pusta, napisz krótko "Brak pozycji w tej sekcji."

Otrzymujesz JSON z wynikami 5 agentów. Zwróć WYŁĄCZNIE fragment HTML, bez ``` i bez wyjaśnień."""


def _load_report_prompt() -> str:
    """Load the live report-composer prompt from the ai-prompt-manager sibling repo.

    Called on EVERY orchestrator run (not just at import) so that a category
    manager editing the prompt in the prompt-manager UI sees the effect on the
    very next "Run daily analysis" click — no Flask restart needed. Cost: one
    small disk read per run. Win: hot-reload of business logic.

    Sibling project layout is assumed to be ../ai-prompt-manager next to this
    one. If the file is missing (standalone setup, prompt-manager not deployed),
    fall back to the in-code constant above. System stays bootable; the prompt
    becomes editable when prompt-manager is co-located.
    """
    pm_file = (Path(__file__).parent.parent.parent / "ai-prompt-manager"
               / "prompts" / "ecommerce-ops" / "desk_briefing_composer.json")
    if not pm_file.exists():
        return _FALLBACK_REPORT_PROMPT
    try:
        import json
        return json.loads(pm_file.read_text(encoding="utf-8"))["active_prompt"]
    except Exception:
        return _FALLBACK_REPORT_PROMPT


async def run_all(target_date: date | None = None) -> tuple[OrchestratorResult, str]:
    """Run all 5 agents in parallel, then compose the HTML report.

    Returns (OrchestratorResult, html_fragment).
    """
    target_date = target_date or date.today()
    snapshot = build_snapshot(target_date)

    start = time.perf_counter()
    results = await asyncio.gather(
        _safe(agent_price_anomaly.run(snapshot), PriceAnomalyReport),
        _safe(agent_deals_anomaly.run(snapshot), DealsAnomalyReport),
        _safe(agent_sales_anomaly.run(snapshot), SalesAnomalyReport),
        _safe(agent_event_manager.run(snapshot), EventManagerReport),
        _safe(agent_click_spike.run(snapshot), ClickSpikeReport),
    )
    runtime = time.perf_counter() - start

    price, deals, sales, events, clicks = results

    aggregated = OrchestratorResult(
        target_date=target_date.isoformat(),
        price=price, deals=deals, sales=sales, events=events, clicks=clicks,
        total_runtime_sec=round(runtime, 2),
    )

    html_fragment = await _compose_html(aggregated)
    return aggregated, html_fragment


async def _safe(coro, expected_type: type[AgentReport]) -> AgentReport:
    """Run a coroutine, capture failures into the expected report type so the orchestrator never crashes."""
    try:
        return await coro
    except Exception as e:
        # Returns an empty but well-typed report carrying the error.
        return expected_type(
            status="error",
            summary=f"Agent failed: {type(e).__name__}",
            error=str(e),
        )


async def _compose_html(aggregated: OrchestratorResult) -> str:
    # Re-read the prompt fresh on every run so prompt-manager edits take
    # effect on the next click — no Flask restart needed.
    prompt = _load_report_prompt()
    payload = aggregated.model_dump()
    return await ask_text(prompt, payload)


def save_report(target_date: date, html_fragment: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"daily_report_{target_date.isoformat()}.html"
    path.write_text(html_fragment, encoding="utf-8")
    return path


# CLI entry point — useful for testing without the Flask UI
async def _main():
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    if "ANTHROPIC_API_KEY" not in os.environ:
        raise SystemExit("ANTHROPIC_API_KEY not set in .env")

    target = date.today()
    print(f"Running 5 agents in parallel for {target}...")
    aggregated, html = await run_all(target)
    print(f"Done in {aggregated.total_runtime_sec}s")
    print(f"  price.anomalies      : {len(aggregated.price.anomalies)}")
    print(f"  deals.anomalies      : {len(aggregated.deals.anomalies)}")
    print(f"  sales.anomalies      : {len(aggregated.sales.anomalies)}")
    print(f"  events.upcoming      : {len(aggregated.events.upcoming)}")
    print(f"  clicks.spikes        : {len(aggregated.clicks.spikes)}")
    path = save_report(target, html)
    print(f"Report saved: {path}")


if __name__ == "__main__":
    asyncio.run(_main())
