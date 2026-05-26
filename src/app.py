"""Flask dashboard for Bazarek Daily Ops Briefing.

Single page: pick a date, click Generate, watch 5 agents run in parallel,
render the resulting HTML report inline. Past reports are listed in the
sidebar for quick navigation.
"""
import asyncio
import os
import sys
import threading
import webbrowser
from datetime import date, datetime
from pathlib import Path
from flask import Flask, abort, render_template, request, send_file
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import run_all, save_report, REPORT_DIR

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PORT = int(os.environ.get("PORT", 5004))

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)


def _existing_reports() -> list[date]:
    """Return sorted list of dates for which a report file exists (newest first)."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dates: list[date] = []
    for p in REPORT_DIR.glob("daily_report_*.html"):
        try:
            iso = p.stem.removeprefix("daily_report_")
            dates.append(date.fromisoformat(iso))
        except ValueError:
            continue
    return sorted(dates, reverse=True)


def _load_report_html(target: date) -> str | None:
    path = REPORT_DIR / f"daily_report_{target.isoformat()}.html"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


@app.template_filter("fmt_date")
def fmt_date(d):
    if isinstance(d, date):
        return d.strftime("%A, %d %B %Y")
    return str(d)


@app.route("/", methods=["GET", "POST"])
def index():
    existing = _existing_reports()
    default_target = existing[0] if existing else date.today()

    requested = request.values.get("date")
    target_date = default_target
    if requested:
        try:
            target_date = datetime.strptime(requested, "%Y-%m-%d").date()
        except ValueError:
            pass

    error = None
    runtime_sec = None
    counts = None

    if request.method == "POST" and request.form.get("action") == "generate":
        if "ANTHROPIC_API_KEY" not in os.environ:
            error = "ANTHROPIC_API_KEY nie jest ustawiony w .env."
        else:
            try:
                aggregated, html = asyncio.run(run_all(target_date))
                save_report(target_date, html)
                runtime_sec = aggregated.total_runtime_sec
                counts = {
                    "price": len(aggregated.price.anomalies),
                    "deals": len(aggregated.deals.anomalies),
                    "sales": len(aggregated.sales.anomalies),
                    "events": len(aggregated.events.upcoming),
                    "clicks": len(aggregated.clicks.spikes),
                }
                existing = _existing_reports()
            except Exception as e:
                error = f"Nie udało się wygenerować raportu: {type(e).__name__}: {e}"

    report_html = _load_report_html(target_date)

    return render_template(
        "dashboard.html",
        target_date=target_date,
        existing=existing,
        report_html=report_html,
        error=error,
        runtime_sec=runtime_sec,
        counts=counts,
    )


@app.route("/report/<iso_date>/raw")
def raw_report(iso_date: str):
    try:
        target = date.fromisoformat(iso_date)
    except ValueError:
        abort(404)
    path = REPORT_DIR / f"daily_report_{target.isoformat()}.html"
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="text/html")


def _open_browser():
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
