"""
SheetCheck API — FastAPI app deployed as a Vercel Python function.

The static front end lives in public/ (served by Vercel's CDN). It uploads
each PDF to /api/parse, then posts every parsed page to /api/check so the
cross-gang checks can see all gangs at once.
"""
import io
import json
import os
from collections import defaultdict
from datetime import date as date_type

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from checks import check_cross_gang_duplicates, run_day_checks
from parser import infer_missing_fields, parse_pdf

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

app = FastAPI(title="SheetCheck")


def _to_json(day):
    """Make a parsed day JSON-safe (date objects → ISO strings)."""
    out = dict(day)
    if isinstance(out.get("date"), date_type):
        out["date"] = out["date"].isoformat()
    return out


def _from_json(day):
    """Restore date objects on a day posted back from the browser."""
    out = dict(day)
    if out.get("date"):
        try:
            out["date"] = date_type.fromisoformat(out["date"])
        except (TypeError, ValueError):
            out["date"] = None
    return out


@app.get("/api/config")
def get_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


@app.post("/api/parse")
async def parse(file: UploadFile = File(...)):
    data = await file.read()
    try:
        days = parse_pdf(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not open {file.filename} as a PDF: {e}")
    days = infer_missing_fields(days)
    for d in days:
        d["_source_file"] = file.filename
    return {"days": [_to_json(d) for d in days]}


@app.post("/api/check")
def check(payload: dict):
    all_pages = [_from_json(d) for d in payload.get("days", [])]

    # Group by gang (from the page header, not which uploader it came from)
    pages_by_gang = defaultdict(list)
    for d in all_pages:
        gang_key = f"Gang {d['gang']}" if d.get("gang") else "Gang ?"
        pages_by_gang[gang_key].append(d)

    for gang_key in pages_by_gang:
        pages_by_gang[gang_key].sort(key=lambda d: d.get("date") or date_type.max)

    all_results = {
        gang_key: [(d, run_day_checks(d)) for d in days]
        for gang_key, days in pages_by_gang.items()
    }

    days_by_date = defaultdict(list)
    for gang_key, days in pages_by_gang.items():
        for day_data in days:
            key = day_data.get("date_str") or f"page_{day_data.get('page')}"
            days_by_date[key].append((gang_key, day_data))

    cross_issues = []
    if len(pages_by_gang) > 1:
        for gang_days in days_by_date.values():
            if len(gang_days) > 1:
                cross_issues += check_cross_gang_duplicates(gang_days)

    all_flat = [i for r in all_results.values() for _, issues in r for i in issues] + cross_issues

    gangs = []
    for gang_label, results in sorted(all_results.items()):
        files = sorted({d.get("_source_file", "") for d, _ in results if d.get("_source_file")})
        gangs.append({
            "label": gang_label,
            "files": files,
            "days": [{"day": _to_json(d), "issues": issues} for d, issues in results],
        })

    return {
        "summary": {
            "errors": sum(1 for i in all_flat if i["severity"] == "error"),
            "warnings": sum(1 for i in all_flat if i["severity"] == "warning"),
            "gangs": len(pages_by_gang),
            "days": sum(len(r) for r in all_results.values()),
        },
        "gangs": gangs,
        "cross_gang": cross_issues if len(pages_by_gang) > 1 else None,
    }


# Local dev only: on Vercel, public/ is served by the CDN before reaching this app.
_PUBLIC = os.path.join(os.path.dirname(__file__), "public")
if os.path.isdir(_PUBLIC):
    app.mount("/", StaticFiles(directory=_PUBLIC, html=True), name="public")
