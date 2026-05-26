# AI E-commerce Ops Assistant

A multi-agent system that produces a morning operations briefing for a category manager on the Nordic e-commerce platform **Bazarek** (markets: Sweden, Norway, Denmark, Finland). Five specialised LLM agents run in parallel via `asyncio.gather()`, each with its own narrow prompt and Pydantic-validated output schema, then an orchestrator stitches their reports into a single executive HTML briefing.

All data is fictional and locally simulated — the project is a portfolio piece, not a production deployment.

## The Problem

A category manager at a multi-country e-commerce platform starts every morning by sifting through five different dashboards:
- Price/offer feed (are accessories getting indexed under the wrong product and dragging down reference prices?)
- Daily deals (any discount that's actually a pricing error?)
- Sales swings (which SKUs jumped or collapsed overnight?)
- Country calendars (Midsommar in 9 days, are we ready?)
- Click telemetry (which products went viral, which spiked from a bot?)

Each takes 5–10 minutes; together it's an hour of context-switching before any real work starts. By the time the manager has a coherent picture, the European session is half done.

## The Solution

Five specialised agents look at the same data in parallel. Each agent is small, focused, and has its own prompt. The orchestrator runs them concurrently and Claude Sonnet 4.6 composes the final briefing.

```
                              ┌──────────────────────────┐
                              │  BazarekSnapshot         │
                              │  (one consistent dataset │
                              │   shared by all agents)  │
                              └────────────┬─────────────┘
                                           │
            ┌────────────┬────────────┬────┴────┬────────────┬────────────┐
            ▼            ▼            ▼         ▼            ▼            ▼
       ┌─────────┐  ┌─────────┐  ┌─────────┐ ┌─────────┐ ┌─────────┐
       │ Agent 1 │  │ Agent 2 │  │ Agent 3 │ │ Agent 4 │ │ Agent 5 │       asyncio.gather()
       │ Price   │  │ Deals   │  │ Sales   │ │ Events  │ │ Clicks  │       → ~5s wall-clock
       │ Anomaly │  │ Anomaly │  │ Anomaly │ │ Manager │ │  Spike  │       (sequentially: ~25s)
       └────┬────┘  └────┬────┘  └────┬────┘ └────┬────┘ └────┬────┘
            └────────────┴────────────┴────┬─────┴────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │  Orchestrator            │
                              │  (fans out, fans in,     │
                              │   Pydantic-validates     │
                              │   each agent's output)   │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │  Claude Sonnet 4.6       │
                              │  composes HTML briefing  │
                              │  · PILNE                 │
                              │  · DO SPRAWDZENIA        │
                              │  · INFORMACYJNE          │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │  output/                 │
                              │   daily_report_<date>.html│
                              │  + Flask dashboard       │
                              └──────────────────────────┘
```

## The 5 Agents

Each agent has exactly one prompt, exactly one Pydantic output schema. None of them know about the others.

| # | Agent | Python does | LLM does |
|---|---|---|---|
| 1 | **Price Anomaly** | Filters offers priced <50% of product base | Decides if offer name semantically matches the product (e.g. *"Leather Case for Phone X"* under *"Phone X Pro"* product → flag) |
| 2 | **Daily Deals Anomaly** | Computes % discount, assigns risk band (>70% HIGH, 50–70% MED, 10–50% LOW) | Writes one-sentence assessment per flagged deal: legitimate promo vs pricing error |
| 3 | **Sales Anomaly** | Computes day-over-day and vs-7-day-avg %; flags ±40% swings | Hypothesises a cause per flagged product, considering the event calendar |
| 4 | **Event Manager** | Filters Nordic event calendar to next 14 days | Writes a category-specific preparation recommendation for each event |
| 5 | **Click Spike** | Computes category leaderboard + day-over-day %; flags 2× dominance or +150% spike | Classifies each spike: organic (viral, launch, event-driven) vs data anomaly worth investigating |

## Design rules visible in the code

| Rule | Where |
|---|---|
| **Agents run in parallel via `asyncio.gather()`** | `orchestrator.py:run_all()` — fan-out + fan-in with safe-wrapped coroutines |
| **One agent = one job = one prompt** | Each `agent_*.py` has a `SYSTEM_PROMPT` constant at the top — easy to find, easy to tweak |
| **Python does math, LLM does interpretation** | Every agent pre-filters and computes thresholds in pure Python before the LLM is even called |
| **Orchestrator doesn't know how agents work** | It calls `.run(snapshot)` and trusts the Pydantic-validated `AgentReport` back |
| **Pydantic with `extra="forbid"`** | If an agent's prompt drifts and returns surprise field names, validation fails loudly |
| **Failure isolation** | One agent crashing returns an error report; the other four still produce useful output |

## Tech stack

- **Python 3.12**
- **Anthropic Claude API** — Haiku 4.5 for agent extraction (cheap, fast, 5 parallel calls), Sonnet 4.6 for final HTML composition (better prose)
- **`asyncio` + `AsyncAnthropic`** — true concurrent agent execution
- **Pydantic 2** — strict output schemas per agent
- **Flask 3** — single-page dashboard with date picker, Run button, and past-report sidebar

## Quick start

```bash
# 1. Clone
git clone https://github.com/bepe92/ai-ecommerce-ops-assistant.git
cd ai-ecommerce-ops-assistant

# 2. Virtual env
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS/Linux

# 3. Install
pip install -r requirements.txt

# 4. Configure
copy .env.example .env           # Windows
# cp .env.example .env           # macOS/Linux
# edit .env and paste your Anthropic API key

# 5. (Optional) Run the orchestrator directly from CLI to test
python src/orchestrator.py

# 6. Start the dashboard (auto-opens at http://localhost:5004)
python src/app.py
```

In the browser: pick a date → click **⚡ Run daily analysis** → watch 5 agents run concurrently → read the AI-composed briefing. Past reports are listed in the sidebar.

## Project layout

```
.
├── src/
│   ├── data_simulator.py        # Deterministic Bazarek snapshot (one dataset → all agents)
│   ├── schemas.py               # Pydantic models for each agent's output + orchestrator result
│   ├── llm_client.py            # Shared AsyncAnthropic wrapper (ask_json / ask_text)
│   ├── agent_price_anomaly.py   # Agent 1
│   ├── agent_deals_anomaly.py   # Agent 2
│   ├── agent_sales_anomaly.py   # Agent 3
│   ├── agent_event_manager.py   # Agent 4
│   ├── agent_click_spike.py     # Agent 5
│   ├── orchestrator.py          # asyncio.gather() + HTML composition
│   └── app.py                   # Flask dashboard
├── templates/dashboard.html
├── static/style.css
├── output/                      # (gitignored) generated HTML reports per date
└── .env                         # (gitignored) ANTHROPIC_API_KEY
```

## What would change for production

| Demo | Production |
|---|---|
| `data_simulator.py` builds a fake snapshot | **Real Bazarek data pipeline** — pull from product catalog DB (price, offers), Snowplow/GA4 (clicks), order-management system (sales) into a single snapshot at 06:00 |
| `python src/app.py` clicked manually | **Scheduled job (Azure Logic App / Container Apps job)** runs the orchestrator at 06:00 every weekday — managers walk into the office, briefing is already in their inbox |
| HTML written to local disk | Briefing emailed via **Microsoft Graph API** + persisted to a **Power BI dataset** for trendable views over weeks/months |
| Local Flask | **Power BI dashboard** for category managers, with the AI-generated narrative embedded as a Text/HTML visual; data drilldowns are native Power BI |
| Anthropic public API | **Azure OpenAI** or Anthropic with EU data residency — commercial pricing data must not freely egress to public APIs |
| 5 hardcoded agents | **Plugin architecture** — each agent is a separate container/function. Adding "Returns Anomaly Detector" is one new file plus an entry in a registry, no orchestrator changes |
| `state.json` style audit trail | **Append-only log to Azure Data Lake** — every agent's input and output stored per run, enabling LLM regression detection and prompt-eval suites |
| Single language (PL) | Per-market briefings (SE/NO/DK/FI) with language and event-calendar localization |

## Why "multi-agent" and not "one big prompt"

Could you do this with one prompt that gets all the data and writes the report? Technically yes, but:
- **Token budget** — five focused prompts each see only their slice; one mega-prompt would push every category into every reasoning step
- **Failure isolation** — if the click-spike agent's prompt has a regression, sales analysis still works
- **Parallelism** — wall-clock time is `max(agent_times)`, not `sum`. With 5 agents at ~2s each, parallel is 2-3s vs sequential 10s
- **Maintainability** — when ops asks "tweak how aggressive the click-spike detection is", you open exactly one file
- **Eval-friendly** — each agent has a clean (input, output) contract that can be regression-tested in isolation

## Roadmap

- [ ] Returns/refunds anomaly agent (#6)
- [ ] Per-market briefings (separate report for SE / NO / DK / FI)
- [ ] Trend memory — agents see *yesterday's* anomaly to detect persistent issues vs one-off blips
- [ ] LangSmith / Phoenix integration for systematic prompt evaluation
- [ ] Plugin architecture so adding agent #6 doesn't touch the orchestrator

## License

Personal project for portfolio / interview demonstration. No license granted for production use.
