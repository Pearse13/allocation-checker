import json
import os
from datetime import datetime
from difflib import get_close_matches

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EXPECTED_HOURS = 10.5
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _prelim_names(config):
    """Return a set of lowercased names that are prelim operatives."""
    return {n.strip().lower() for n in config.get("prelim_operatives", {}).keys()}


def _issue(severity, check, message, day=None, gang=None):
    return {"severity": severity, "check": check, "message": message, "day": day, "gang": gang}


# ---------------------------------------------------------------------------
# Per-day checks (no config needed)
# ---------------------------------------------------------------------------

def check_hours(day_data):
    """Every labour and plant row total must equal EXPECTED_HOURS."""
    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    for section, entries in [("Labour", day_data.get("labour", [])), ("Plant", day_data.get("plant", []))]:
        for entry in entries:
            name = entry["name"]
            stated = entry["stated_total"]
            calc = entry["calculated_total"]

            if stated == 0:
                continue  # Zero-hour rows are handled by the roster check

            if stated != EXPECTED_HOURS:
                issues.append(_issue(
                    "error", "hours",
                    f"{section} — {name}: total column shows {stated}, expected {EXPECTED_HOURS}. Please check.",
                    day=label, gang=gang
                ))

            if round(calc, 2) != stated:
                issues.append(_issue(
                    "error", "hours_maths",
                    f"{section} — {name}: job hours add up to {calc} but total column shows {stated}. Maths doesn't match.",
                    day=label, gang=gang
                ))

    return issues


def check_date(day_data):
    """Verify the written day name matches the actual date."""
    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    day_name = day_data.get("day")
    date_obj = day_data.get("date")

    if not day_name:
        issues.append(_issue("warning", "date", "Could not read day name from sheet.", day=label, gang=gang))
        return issues

    if not date_obj:
        issues.append(_issue("warning", "date", f"Could not read date from sheet (day written as {day_name}).", day=label, gang=gang))
        return issues

    actual_day = date_obj.strftime("%A")
    if actual_day != day_name:
        issues.append(_issue(
            "error", "date",
            f"Day says '{day_name}' but {day_data['date_str']} is actually a {actual_day}. Please check the date.",
            day=label, gang=gang
        ))

    return issues


def check_times(day_data):
    """Start time must be 0800 and finish time must be 1800."""
    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    start = day_data.get("start_time")
    finish = day_data.get("finish_time")

    if not start:
        issues.append(_issue("warning", "times", "Start time is missing from the sheet.", day=label, gang=gang))
    elif start != "0800":
        issues.append(_issue("error", "times", f"Start time shows {start}, expected 0800. Please check.", day=label, gang=gang))

    if not finish:
        issues.append(_issue("warning", "times", "Finish time is missing from the sheet.", day=label, gang=gang))
    elif finish != "1800":
        issues.append(_issue("error", "times", f"Finish time shows {finish}, expected 1800. Please check.", day=label, gang=gang))

    return issues


def check_prelim_operatives(day_data):
    """
    Peter Giblin and Mick Kilcoyne (prelim operatives) must always have:
      - Job 1 = 0.5 (daily briefing)
      - Job 2 = 10.0 (supervision duties)
      - Nothing else
    """
    config = _load_config()
    prelims = config.get("prelim_operatives", {})
    if not prelims:
        return []

    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    # Build lookup of labour entries by lowercase name
    labour_by_name = {e["name"].strip().lower(): e for e in day_data.get("labour", [])}

    for prelim_name, rules in prelims.items():
        key = prelim_name.strip().lower()
        expected = rules.get("expected_job_hours", {})  # {"1": 0.5, "2": 10.0}

        if key not in labour_by_name:
            issues.append(_issue(
                "error", "prelim_operative",
                f"Prelim — {prelim_name} is missing from this sheet. They should appear on every gang every day.",
                day=label, gang=gang
            ))
            continue

        entry = labour_by_name[key]
        job_hours = entry["job_hours"]  # list indexed 0-9 = job columns 1-10

        for job_num_str, expected_hrs in expected.items():
            col_idx = int(job_num_str) - 1  # job "1" is index 0
            actual = job_hours[col_idx] if col_idx < len(job_hours) else 0.0
            if actual != expected_hrs:
                issues.append(_issue(
                    "error", "prelim_operative",
                    f"Prelim — {prelim_name}: Job {job_num_str} should be {expected_hrs}hrs but shows {actual}hrs. "
                    f"Prelim hours must be 0.5 (briefing) + 10 (supervision) only.",
                    day=label, gang=gang
                ))

        # Check no hours outside the expected jobs
        for idx, hrs in enumerate(job_hours):
            job_num = idx + 1
            if hrs != 0 and str(job_num) not in expected:
                issues.append(_issue(
                    "error", "prelim_operative",
                    f"Prelim — {prelim_name} has {hrs}hrs in Job {job_num}, but prelim hours should only be "
                    f"Job 1 (briefing) and Job 2 (supervision). Please check.",
                    day=label, gang=gang
                ))

    return issues


def check_known_operatives(day_data):
    """
    Check every operative on the sheet against the master known_operatives list.
    - Flag anyone not on the list (unknown — may need adding to config)
    - Flag anyone listed with 0 total hours (should be removed or filled in)
    - Flag anyone whose trade doesn't match their expected trade
    """
    config = _load_config()
    prelim_names = _prelim_names(config)
    known = {e["name"].strip().lower(): e for e in config.get("known_operatives", [])}

    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    for entry in day_data.get("labour", []):
        key = entry["name"].strip().lower()

        if key in prelim_names:
            continue  # Prelims checked separately

        # Zero hours
        if entry["stated_total"] == 0:
            issues.append(_issue(
                "warning", "operatives",
                f"Labour — {entry['name']} is listed but has 0 total hours. "
                f"Remove from the sheet or fill in their hours.",
                day=label, gang=gang
            ))
            continue

        # Unknown operative
        if key not in known:
            close = get_close_matches(key, known.keys(), n=1, cutoff=0.8)
            suggestion = (" Did you mean '" + known[close[0]]["name"] + "'?") if close else ""
            issues.append(_issue(
                "warning", "operatives",
                f"Labour — {entry['name']} is not on the known operatives list.{suggestion} "
                f"If they are a new or temporary worker, add them to settings.",
                day=label, gang=gang
            ))
            continue

        # Trade mismatch
        expected_trade = known[key]["trade"]
        actual_trade = entry.get("trade", "").strip()
        if actual_trade.lower() != expected_trade.lower():
            issues.append(_issue(
                "error", "trade",
                f"Labour — {entry['name']}: trade listed as '{actual_trade}' "
                f"but expected '{expected_trade}'. Please correct.",
                day=label, gang=gang
            ))

    return issues


def check_known_plant(day_data):
    """
    Check every plant item against the master known_plant list.
    - Prelim plant (Ford Ranger, Micks MAN LWB) is skipped — handled separately.
    - Flag anything not on the list.
    - Flag any plant row with 0 total hours.
    """
    config = _load_config()
    prelim_plant = {p.strip().lower() for p in config.get("prelim_plant", [])}
    known = {p.strip().lower() for p in config.get("known_plant", [])}

    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    for entry in day_data.get("plant", []):
        key = entry["name"].strip().lower()

        if key in prelim_plant:
            continue

        if entry["stated_total"] == 0:
            issues.append(_issue(
                "warning", "plant",
                f"Plant — {entry['name']} is listed but has 0 total hours. "
                f"Remove from the sheet or fill in its hours.",
                day=label, gang=gang
            ))
            continue

        if key not in known:
            close = get_close_matches(key, known, n=1, cutoff=0.8)
            if close:
                original = next(p for p in config["known_plant"] if p.strip().lower() == close[0])
                suggestion = f" Did you mean '{original}'?"
            else:
                suggestion = ""
            issues.append(_issue(
                "warning", "plant",
                f"Plant — '{entry['name']}' is not on the known plant list.{suggestion} "
                f"Check the name for typos, or add it to settings if it's new.",
                day=label, gang=gang
            ))

    return issues


def check_required_plant(day_data):
    """Every sheet must include Hand Tools, a Stihl Saw, and a set of chains."""
    config = _load_config()
    groups = config.get("required_plant_groups", [])
    if not groups:
        return []

    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    plant_on_sheet = {e["name"].strip().lower() for e in day_data.get("plant", []) if e["stated_total"] > 0}

    for group in groups:
        variants = {v.lower() for v in group.get("variants", [])}
        if not variants & plant_on_sheet:
            issues.append(_issue(
                "error", "required_plant",
                f"Plant — {group['label']} is missing from this sheet. It must appear on every gang every day.",
                day=label, gang=gang
            ))

    return issues


def check_duplicates_within_sheet(day_data):
    """Flag any name appearing more than once in labour or plant."""
    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    for section, entries in [("Labour", day_data.get("labour", [])), ("Plant", day_data.get("plant", []))]:
        seen = {}
        for entry in entries:
            name = entry["name"].strip().lower()
            seen[name] = seen.get(name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                issues.append(_issue(
                    "error", "duplicates",
                    f"{section} — '{name.title()}' appears {count} times on this sheet. Remove the duplicate.",
                    day=label, gang=gang
                ))

    return issues



def check_formatting(day_data):
    """Flag blank entries and obvious formatting problems."""
    issues = []
    label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"
    gang = day_data.get("gang")

    for section, entries in [("Labour", day_data.get("labour", [])), ("Plant", day_data.get("plant", []))]:
        for entry in entries:
            name = entry["name"].strip()

            if not name or name in ("0", "None", "-"):
                issues.append(_issue(
                    "warning", "formatting",
                    f"{section} — row with hours {entry['stated_total']} has no name. Please check.",
                    day=label, gang=gang
                ))

            if section == "Labour" and not entry.get("trade"):
                issues.append(_issue(
                    "warning", "formatting",
                    f"Labour — {name} has no trade listed. Please add.",
                    day=label, gang=gang
                ))

            if not entry.get("employer"):
                issues.append(_issue(
                    "warning", "formatting",
                    f"{section} — {name} has no employer listed. Please add.",
                    day=label, gang=gang
                ))

            all_nums = entry["job_hours"] + [entry["stated_total"]]
            for h in all_nums:
                if h % 0.5 != 0:
                    issues.append(_issue(
                        "warning", "formatting",
                        f"{section} — {name} has an unusual hour value ({h}). Hours are normally in 0.5 increments.",
                        day=label, gang=gang
                    ))
                    break

    return issues


def run_day_checks(day_data):
    """Run all per-day checks."""
    if day_data.get("parse_error"):
        return [_issue("error", "parse", f"Could not read page {day_data.get('page', '?')}: {day_data['parse_error']}")]

    issues = []
    issues += check_date(day_data)
    issues += check_times(day_data)
    issues += check_hours(day_data)
    issues += check_prelim_operatives(day_data)
    issues += check_known_operatives(day_data)
    issues += check_known_plant(day_data)
    issues += check_required_plant(day_data)
    issues += check_duplicates_within_sheet(day_data)
    issues += check_formatting(day_data)
    return issues


# ---------------------------------------------------------------------------
# Cross-gang checks
# ---------------------------------------------------------------------------

def check_cross_gang_duplicates(all_gang_days):
    """
    all_gang_days: list of (gang_label, day_data) tuples for a single calendar day.
    Flags duplicates across gangs, excluding prelim operatives who legitimately
    appear on all gangs.
    """
    config = _load_config()
    prelim_names = _prelim_names(config)
    prelim_plant = {p.strip().lower() for p in config.get("prelim_plant", [])}

    issues = []
    labour_seen = {}  # name_lower -> gang_label
    plant_seen = {}

    for gang_label, day_data in all_gang_days:
        label = f"{day_data.get('day', '?')} {day_data.get('date_str', '')}"

        for entry in day_data.get("labour", []):
            key = entry["name"].strip().lower()
            if key in prelim_names:
                continue  # Expected on all gangs — not a duplicate
            if key in labour_seen:
                issues.append(_issue(
                    "error", "cross_gang_duplicate",
                    f"Labour — '{entry['name']}' appears in both {labour_seen[key]} and {gang_label} on {label}. "
                    f"Someone is on two sheets — please check.",
                    day=label
                ))
            else:
                labour_seen[key] = gang_label

        for entry in day_data.get("plant", []):
            key = entry["name"].strip().lower()
            if key in prelim_plant:
                continue  # Expected on all gangs — not a duplicate
            if key in plant_seen:
                issues.append(_issue(
                    "error", "cross_gang_duplicate",
                    f"Plant — '{entry['name']}' appears in both {plant_seen[key]} and {gang_label} on {label}. "
                    f"Same item on two sheets — please check.",
                    day=label
                ))
            else:
                plant_seen[key] = gang_label

    return issues
