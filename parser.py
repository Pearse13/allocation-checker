"""
Parser for ACS Civils allocation sheet PDFs (Excel-generated, fixed template).

Table column layout (19 columns total):
  0  = Name / Plant Type
  1  = Trade (labour) / None (plant)
  2  = Employer / Owner
  3-12 = Job hour columns 1-10
  13 = Total
  14 = JOB No (links to description)
  15 = Description of work
  16-18 = (overflow / merged description cells)

Header rows:
  Row 0: Project Name, Client, Day, Date
  Row 1: Gang, Area, Start Time, Finish Time
  Row 2: Column headers
  Row 3+: Labour data rows
  Row N (PLANT TYPE): Plant section header
  Last row: Signature
"""
import pdfplumber
import re
from datetime import datetime, timedelta

JOB_COLS = list(range(3, 13))   # columns 3-12 = job hours 1-10
TOTAL_COL = 13
DESC_JOB_COL = 14
DESC_TEXT_COL = 15

TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
}


def _c(val):
    """Clean cell value to string."""
    return str(val).strip() if val is not None else ""


def _num(val):
    """Convert cell to float, or None."""
    try:
        return float(_c(val))
    except ValueError:
        return None


def _parse_header(rows):
    """Extract metadata from rows 0 and 1."""
    header = {
        "gang": None, "day": None, "date": None, "date_str": None,
        "start_time": None, "finish_time": None,
        "area": None, "client": None, "project": None,
    }

    for row in rows:
        cells = [_c(c) for c in row]
        flat = " ".join(cells)

        # Gang: row starting with 'Gang', value in col 1
        if cells[0] == "Gang" and len(cells) > 1 and cells[1]:
            header["gang"] = cells[1]

        # Day and Date
        for i, cell in enumerate(cells):
            if cell == "Day" and i + 1 < len(cells):
                header["day"] = cells[i + 1]
            if cell == "Date" and i + 1 < len(cells):
                header["date_str"] = cells[i + 1]
            if cell == "Start Time" and i + 1 < len(cells):
                header["start_time"] = cells[i + 1]
            if cell == "Finish Time" and i + 1 < len(cells):
                header["finish_time"] = cells[i + 1]
            if cell == "Client" and i + 2 < len(cells):
                # Client value is a few columns over
                for j in range(i + 1, min(i + 6, len(cells))):
                    if cells[j]:
                        header["client"] = cells[j]
                        break
            if cell == "Area" and i + 2 < len(cells):
                for j in range(i + 1, min(i + 8, len(cells))):
                    if cells[j]:
                        header["area"] = cells[j]
                        break

        # Project name
        if cells[0] == "Project Name:" and len(cells) > 1 and cells[1]:
            header["project"] = cells[1]

    # Parse date string to date object
    if header["date_str"]:
        try:
            header["date"] = datetime.strptime(header["date_str"], "%d/%m/%Y").date()
        except ValueError:
            pass

    return header


def _parse_entry(row, is_plant=False):
    """Parse a single labour or plant data row. Returns dict or None."""
    cells = [_c(c) for c in row]
    if not cells:
        return None

    name = cells[0]
    if not name:
        return None

    # Skip section headers and signature row
    skip_keywords = ("LABOUR", "PLANT TYPE", "TRADE", "EMPLOYER", "TOTAL",
                     "OWNER", "JOB", "DESCRIPTION", "CONTRACTOR", "SIGNATURE",
                     "WORKS MANAGER")
    if any(kw in name.upper() for kw in skip_keywords):
        return None

    # Skip fully empty / zero rows
    job_vals = [_num(cells[col]) for col in JOB_COLS if col < len(cells)]
    job_vals = [v for v in job_vals if v is not None]
    stated_total = _num(cells[TOTAL_COL]) if TOTAL_COL < len(cells) else None

    if stated_total is None and not job_vals:
        return None

    # All zeros with no real name = blank template row, skip it
    # But keep rows where a real name is present (e.g. someone listed with 0 hours)
    name_looks_real = len(name.split()) >= 2 or (len(name) > 3 and name[0].isupper())
    if stated_total == 0 and all(v == 0 for v in job_vals) and not name_looks_real:
        return None

    job_hours = []
    for col in JOB_COLS:
        v = _num(cells[col]) if col < len(cells) else None
        job_hours.append(v if v is not None else 0.0)

    calc_total = round(sum(job_hours), 2)
    stated_total = stated_total if stated_total is not None else 0.0

    trade = cells[1] if not is_plant and len(cells) > 1 else ""
    employer = cells[2] if len(cells) > 2 else ""

    return {
        "name": name,
        "trade": trade,
        "employer": employer,
        "job_hours": job_hours,
        "stated_total": stated_total,
        "calculated_total": calc_total,
    }


def _parse_page(page):
    """Parse one page of the PDF."""
    tables = page.extract_tables(TABLE_SETTINGS)
    if not tables:
        return {"parse_error": "No table found on this page"}

    table = max(tables, key=lambda t: len(t))

    # Rows 0-1 are header, row 2 is column labels
    header = _parse_header(table[:2])

    labour = []
    plant = []
    job_descriptions = {}
    in_plant = False

    for row in table[2:]:
        cells = [_c(c) for c in row]
        if not cells:
            continue

        name = cells[0]

        # Section switch
        if "PLANT TYPE" in name.upper():
            in_plant = True
            continue

        # Signature row → done (signature cell contains both name and "CONTRACTOR")
        if "CONTRACTOR" in name.upper() or "SIGNATURE" in name.upper():
            break

        # Job description (col 14 = job number, col 15 = text)
        if DESC_JOB_COL < len(cells) and DESC_TEXT_COL < len(cells):
            job_ref = cells[DESC_JOB_COL]
            desc_text = cells[DESC_TEXT_COL]
            if job_ref and re.match(r"^\d{1,2}$", job_ref) and desc_text:
                job_descriptions[int(job_ref)] = desc_text

        entry = _parse_entry(row, is_plant=in_plant)
        if entry:
            (plant if in_plant else labour).append(entry)

    return {
        **header,
        "labour": labour,
        "plant": plant,
        "job_descriptions": job_descriptions,
        "parse_error": None,
    }


_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def infer_missing_fields(days):
    """
    Fill in missing gang or date fields using context from other pages in the
    same file.  Called once per uploaded file after parse_pdf().

    Gang inference:
      - Single-gang file  → any page missing a gang gets the file's gang.
      - Combined file     → nearest neighbour by page index.

    Date inference:
      - If day name is present, find the nearest dated page in the file and
        calculate the date from the day-name difference (e.g. if Mon=21/09
        then Tue must be 22/09).
    """
    from collections import Counter

    # ── Gang ──────────────────────────────────────────────────────────
    known_gangs = {d["gang"] for d in days if d.get("gang")}

    if len(known_gangs) == 1:
        sole = next(iter(known_gangs))
        for d in days:
            if not d.get("gang"):
                d["gang"] = sole
                d["gang_inferred"] = True

    elif len(known_gangs) > 1:
        for i, d in enumerate(days):
            if d.get("gang"):
                continue
            for offset in range(1, len(days)):
                for j in (i - offset, i + offset):
                    if 0 <= j < len(days) and days[j].get("gang"):
                        d["gang"] = days[j]["gang"]
                        d["gang_inferred"] = True
                        break
                if d.get("gang"):
                    break

    # ── Date ──────────────────────────────────────────────────────────
    anchors = [
        (i, d["date"], d.get("day"))
        for i, d in enumerate(days)
        if d.get("date") and not d.get("date_inferred")
    ]

    for i, d in enumerate(days):
        if d.get("date"):
            continue
        target_day = d.get("day")
        if not target_day or target_day not in _DAY_ORDER:
            continue
        if not anchors:
            continue

        # Nearest anchor by page index
        _, ref_date, ref_day = min(anchors, key=lambda x: abs(x[0] - i))
        if not ref_day or ref_day not in _DAY_ORDER:
            continue

        diff = _DAY_ORDER.index(target_day) - _DAY_ORDER.index(ref_day)
        inferred = ref_date + timedelta(days=diff)
        d["date"]          = inferred
        d["date_str"]      = inferred.strftime("%d/%m/%Y")
        d["date_inferred"] = True

    return days


def parse_pdf(pdf_file):
    """
    Parse an allocation sheet PDF (one or more pages = one or more days).
    Returns list of day-dicts.
    """
    days = []
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                data = _parse_page(page)
                data["page"] = i + 1
                days.append(data)
            except Exception as e:
                days.append({"parse_error": str(e), "page": i + 1})
    return days
