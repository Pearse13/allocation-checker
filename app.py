"""
SheetCheck API — FastAPI app deployed as a Vercel Python function.

The static front end lives in public/ (served by Vercel's CDN). It uploads
each PDF to /api/parse, then posts every parsed page to /api/check so the
cross-gang checks can see all gangs at once.
"""
import hmac
import io
import os
from collections import defaultdict
from datetime import date as date_type

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from checks import check_cross_gang_duplicates, check_plant_dropoffs, find_unseen_plant, run_day_checks
from parser import infer_missing_fields, parse_pdf
from storage import load_config, save_config

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
    return load_config()


def _remove(items, name):
    key = name.strip().lower()
    return [i for i in items if i.strip().lower() != key]


@app.post("/api/config/update")
def update_config(payload: dict):
    """
    Add to or remove from the known lists. Requires the SHEETCHECK_PASSCODE.
      {"action": "add_operative", "name": ..., "trade": ...}
      {"action": "add_plant", "name": ..., "vehicle": bool}
      {"action": "offhire", "name": ...}
    """
    expected = os.environ.get("SHEETCHECK_PASSCODE")
    if not expected:
        raise HTTPException(status_code=503, detail="Editing is not set up yet (no passcode configured).")
    if not hmac.compare_digest(str(payload.get("passcode", "")), expected):
        raise HTTPException(status_code=401, detail="Wrong passcode.")

    action = payload.get("action")
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")

    config = load_config()
    if action == "add_operative":
        trade = str(payload.get("trade", "")).strip()
        if not trade:
            raise HTTPException(status_code=400, detail="Trade is required.")
        ops = [o for o in config.get("known_operatives", []) if o["name"].strip().lower() != name.lower()]
        config["known_operatives"] = ops + [{"name": name, "trade": trade}]
        message = f"Added {name} ({trade}) to the labour roster."
    elif action == "add_plant":
        config["known_plant"] = _remove(config.get("known_plant", []), name) + [name]
        if payload.get("vehicle"):
            config["vehicle_plant"] = _remove(config.get("vehicle_plant", []), name) + [name]
        message = f"Added {name} to the known plant list."
    elif action == "offhire":
        for list_name in ("known_plant", "vehicle_plant", "prelim_plant"):
            config[list_name] = _remove(config.get(list_name, []), name)
        message = f"{name} marked as offhired and removed from the known plant list."
    else:
        raise HTTPException(status_code=400, detail="Unknown action.")

    save_config(config)
    return {"ok": True, "message": message}


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
    config = load_config()
    all_pages = [_from_json(d) for d in payload.get("days", [])]

    # Group by gang (from the page header, not which uploader it came from)
    pages_by_gang = defaultdict(list)
    for d in all_pages:
        gang_key = f"Gang {d['gang']}" if d.get("gang") else "Gang ?"
        pages_by_gang[gang_key].append(d)

    for gang_key in pages_by_gang:
        pages_by_gang[gang_key].sort(key=lambda d: d.get("date") or date_type.max)

    all_results = {
        gang_key: [(d, run_day_checks(d, config)) for d in days]
        for gang_key, days in pages_by_gang.items()
    }

    dropoffs = check_plant_dropoffs(pages_by_gang, config)
    for gang_key, idx, issue in dropoffs:
        all_results[gang_key][idx][1].append(issue)
    unseen_plant = find_unseen_plant(all_pages, config, exclude=[i["action"]["name"] for _, _, i in dropoffs])

    days_by_date = defaultdict(list)
    for gang_key, days in pages_by_gang.items():
        for day_data in days:
            key = day_data.get("date_str") or f"page_{day_data.get('page')}"
            days_by_date[key].append((gang_key, day_data))

    cross_issues = []
    if len(pages_by_gang) > 1:
        for gang_days in days_by_date.values():
            if len(gang_days) > 1:
                cross_issues += check_cross_gang_duplicates(gang_days, config)

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
        "unseen_plant": unseen_plant,
    }


# Local dev only: on Vercel, public/ is served by the CDN before reaching this app.
_PUBLIC = os.path.join(os.path.dirname(__file__), "public")
if os.path.isdir(_PUBLIC):
    app.mount("/", StaticFiles(directory=_PUBLIC, html=True), name="public")
