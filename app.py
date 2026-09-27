import base64
import streamlit as st
from collections import defaultdict
from parser import parse_pdf
from checks import run_day_checks, check_cross_gang_duplicates

st.set_page_config(page_title="SheetCheck", layout="wide", page_icon="🟠")

with open("hero.jpg", "rb") as f:
    hero_b64 = base64.b64encode(f.read()).decode()

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    #MainMenu, footer, header {{ visibility: hidden; }}

    /* Page container */
    .block-container {{
        padding: 0 3.5rem 5rem !important;
        max-width: 1160px !important;
    }}

    /* ── Hero ────────────────────────────────────── */
    .sc-hero {{
        margin: 0 -3.5rem 0;
        background:
            linear-gradient(160deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.78) 100%),
            url("data:image/jpeg;base64,{hero_b64}") center 38% / cover no-repeat;
        padding: 110px 3.5rem 68px;
        min-height: 420px;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }}

    .sc-pill {{
        display: inline-flex;
        align-items: center;
        background: rgba(245,158,11,0.12);
        border: 1px solid rgba(245,158,11,0.28);
        color: #f59e0b;
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        padding: 5px 13px;
        border-radius: 100px;
        margin-bottom: 22px;
        width: fit-content;
    }}

    .sc-hero-title {{
        font-size: 3.75rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.04em;
        line-height: 1;
        margin-bottom: 16px;
    }}

    .sc-hero-sub {{
        font-size: 1rem;
        color: rgba(255,255,255,0.5);
        max-width: 420px;
        line-height: 1.65;
    }}

    /* ── Section labels ──────────────────────────── */
    .sc-label {{
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #f59e0b;
        margin: 44px 0 14px;
    }}

    /* ── Upload cards ────────────────────────────── */
    [data-testid="stFileUploader"] {{
        background: #141726;
        border: 1px solid #1d2035;
        border-radius: 14px;
        padding: 4px 4px 8px;
    }}
    [data-testid="stFileUploader"] label p {{
        font-size: 0.7rem !important;
        font-weight: 700 !important;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.12em;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        background: transparent !important;
        border: 1.5px dashed #252840 !important;
        border-radius: 10px !important;
        min-height: 90px;
        transition: border-color 0.2s, background 0.2s;
    }}
    [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: rgba(245,158,11,0.45) !important;
        background: rgba(245,158,11,0.03) !important;
    }}
    [data-testid="stFileUploaderDropzoneInstructions"] div span {{
        color: #475569 !important;
        font-size: 0.78rem !important;
    }}
    [data-testid="stFileUploaderDropzoneInstructions"] div small {{
        color: #334155 !important;
        font-size: 0.7rem !important;
    }}

    /* ── Run button ──────────────────────────────── */
    div[data-testid="stButton"] > button[kind="primary"] {{
        background: #f59e0b !important;
        color: #0a0c14 !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.03em;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 2.25rem !important;
        margin-top: 22px;
        box-shadow: 0 0 0 0 rgba(245,158,11,0);
        transition: box-shadow 0.2s, transform 0.15s;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        background: #d97706 !important;
        box-shadow: 0 8px 28px rgba(245,158,11,0.3) !important;
    }}

    /* ── Divider ─────────────────────────────────── */
    .sc-rule {{
        height: 1px;
        background: #1d2035;
        margin: 0 -3.5rem;
        border: none;
    }}

    /* ── Summary metrics ─────────────────────────── */
    .sc-metrics {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin: 44px 0 52px;
    }}
    .sc-metric {{
        background: #141726;
        border: 1px solid #1d2035;
        border-radius: 14px;
        padding: 24px 26px 22px;
    }}
    .sc-metric-val {{
        font-size: 2.75rem;
        font-weight: 800;
        line-height: 1;
        letter-spacing: -0.04em;
        font-variant-numeric: tabular-nums;
    }}
    .sc-metric-lbl {{
        font-size: 0.62rem;
        color: #475569;
        margin-top: 10px;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-weight: 600;
    }}
    .col-red   {{ color: #ef4444; }}
    .col-amber {{ color: #f59e0b; }}
    .col-green {{ color: #22c55e; }}
    .col-white {{ color: #e2e8f0; }}

    /* ── Gang section header ─────────────────────── */
    .sc-gang {{
        display: flex;
        align-items: baseline;
        gap: 10px;
        margin: 48px 0 14px;
        padding-bottom: 12px;
        border-bottom: 1px solid #1d2035;
    }}
    .sc-gang-name {{
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #f59e0b;
    }}
    .sc-gang-file {{
        font-size: 0.75rem;
        color: #334155;
        font-weight: 400;
    }}

    /* ── Expanders ───────────────────────────────── */
    [data-testid="stExpander"] {{
        background: #141726 !important;
        border: 1px solid #1d2035 !important;
        border-radius: 12px !important;
        margin-bottom: 8px !important;
        overflow: hidden !important;
    }}
    [data-testid="stExpander"] summary {{
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: #cbd5e1 !important;
        padding: 14px 18px !important;
        line-height: 1.4 !important;
    }}
    [data-testid="stExpander"] summary:hover {{
        color: #f1f5f9 !important;
    }}
    [data-testid="stExpander"] details[open] summary {{
        border-bottom: 1px solid #1d2035;
    }}
    [data-testid="stExpander"] .streamlit-expanderContent {{
        padding: 16px 18px !important;
    }}

    /* ── Issue cards ─────────────────────────────── */
    .issue-error {{
        background: rgba(239,68,68,0.07);
        border-left: 3px solid #ef4444;
        padding: 11px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 7px;
        font-size: 0.875rem;
        color: #fca5a5;
        line-height: 1.55;
    }}
    .issue-warning {{
        background: rgba(245,158,11,0.07);
        border-left: 3px solid #f59e0b;
        padding: 11px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 7px;
        font-size: 0.875rem;
        color: #fcd34d;
        line-height: 1.55;
    }}
    .issue-label {{
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.6rem;
        letter-spacing: 0.14em;
        margin-bottom: 5px;
        opacity: 0.5;
    }}
</style>
""", unsafe_allow_html=True)

CHECK_LABELS = {
    "hours":                "Hours total",
    "hours_maths":          "Hours maths",
    "date":                 "Date / day",
    "times":                "Start / finish",
    "prelim_operative":     "Prelim operative",
    "operatives":           "Unknown operative",
    "trade":                "Trade mismatch",
    "plant":                "Unknown plant",
    "required_plant":       "Required plant",
    "duplicates":           "Duplicate",
    "cross_gang_duplicate": "Cross-gang duplicate",
    "formatting":           "Formatting",
    "parse":                "Parse error",
}


def render_issue(issue):
    label = CHECK_LABELS.get(issue["check"], issue["check"].replace("_", " ").title())
    cls  = "issue-error"   if issue["severity"] == "error" else "issue-warning"
    icon = "❌"            if issue["severity"] == "error" else "⚠️"
    st.markdown(
        f'<div class="{cls}"><div class="issue-label">{icon}&nbsp;&nbsp;{label}</div>{issue["message"]}</div>',
        unsafe_allow_html=True,
    )


def fmt_day(day_data):
    day  = day_data.get("day") or f"Page {day_data.get('page', '?')}"
    date = day_data.get("date_str", "")
    return f"{day}  {date}".strip()


def badge(issues):
    errors   = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    if not issues:
        return "✅ Clear"
    parts = []
    if errors:
        parts.append(f"❌ {len(errors)} error{'s' if len(errors) > 1 else ''}")
    if warnings:
        parts.append(f"⚠️ {len(warnings)} warning{'s' if len(warnings) > 1 else ''}")
    return "  ".join(parts)


# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="sc-hero">
    <div class="sc-pill">ACS Civils</div>
    <div class="sc-hero-title">SheetCheck</div>
    <div class="sc-hero-sub">Catches errors in your daily allocation sheets before they're signed off.</div>
</div>
""", unsafe_allow_html=True)

# ── Upload ────────────────────────────────────────────────────────────────────
st.markdown('<div class="sc-label">Upload gang PDFs — one per gang</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
uploads = {}
with c1:
    f = st.file_uploader("Gang 1", type="pdf", key="gang1")
    if f: uploads["Gang 1"] = f
with c2:
    f = st.file_uploader("Gang 2", type="pdf", key="gang2")
    if f: uploads["Gang 2"] = f
with c3:
    f = st.file_uploader("Gang 3", type="pdf", key="gang3")
    if f: uploads["Gang 3"] = f

run = st.button("Run Checks →", type="primary", disabled=not uploads)

if not uploads or not run:
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────────────
all_parsed = {}
with st.spinner("Reading PDFs…"):
    for gang_label, pdf_file in uploads.items():
        all_parsed[gang_label] = parse_pdf(pdf_file)

# ── Run checks ────────────────────────────────────────────────────────────────
all_results = {}
for gang_label, days in all_parsed.items():
    all_results[gang_label] = [(d, run_day_checks(d)) for d in days]

days_by_date = defaultdict(list)
for gang_label, days in all_parsed.items():
    for day_data in days:
        key = day_data.get("date_str") or f"page_{day_data.get('page')}"
        days_by_date[key].append((gang_label, day_data))

cross_issues = []
if len(all_parsed) > 1:
    for key, gang_days in days_by_date.items():
        if len(gang_days) > 1:
            cross_issues += check_cross_gang_duplicates(gang_days)

all_flat      = [i for r in all_results.values() for _, issues in r for i in issues] + cross_issues
total_errors  = sum(1 for i in all_flat if i["severity"] == "error")
total_warns   = sum(1 for i in all_flat if i["severity"] == "warning")
total_days    = sum(len(r) for r in all_results.values())

# ── Divider ───────────────────────────────────────────────────────────────────
st.markdown('<hr class="sc-rule">', unsafe_allow_html=True)

# ── Summary ───────────────────────────────────────────────────────────────────
st.markdown('<div class="sc-label" style="margin-top:44px">Summary</div>', unsafe_allow_html=True)

ec = "col-red"   if total_errors else "col-green"
wc = "col-amber" if total_warns  else "col-green"
gangs_str = f"{len(uploads)} gang{'s' if len(uploads) > 1 else ''}"
days_str  = f"{total_days} day{'s' if total_days > 1 else ''}"

st.markdown(f"""
<div class="sc-metrics">
    <div class="sc-metric">
        <div class="sc-metric-val {ec}">{total_errors}</div>
        <div class="sc-metric-lbl">Errors</div>
    </div>
    <div class="sc-metric">
        <div class="sc-metric-val {wc}">{total_warns}</div>
        <div class="sc-metric-lbl">Warnings</div>
    </div>
    <div class="sc-metric">
        <div class="sc-metric-val col-white">{total_days}</div>
        <div class="sc-metric-lbl">{gangs_str} · {days_str} checked</div>
    </div>
</div>
""", unsafe_allow_html=True)

if total_errors == 0 and total_warns == 0:
    st.success("All checks passed across every sheet.")

# ── Per-gang results ──────────────────────────────────────────────────────────
for gang_label, results in all_results.items():
    fname = uploads[gang_label].name
    st.markdown(f"""
    <div class="sc-gang">
        <span class="sc-gang-name">{gang_label}</span>
        <span class="sc-gang-file">{fname}</span>
    </div>
    """, unsafe_allow_html=True)

    for day_data, issues in results:
        errors   = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        label    = f"{fmt_day(day_data)}  —  {badge(issues)}"

        with st.expander(label, expanded=bool(issues)):
            if not issues:
                st.markdown('<p style="color:#22c55e;font-size:0.875rem;margin:0">No issues found.</p>', unsafe_allow_html=True)
            else:
                for issue in errors:
                    render_issue(issue)
                for issue in warnings:
                    render_issue(issue)

            labour = day_data.get("labour", [])
            plant  = day_data.get("plant",  [])
            if labour or plant:
                with st.expander("View parsed data", expanded=False):
                    d1, d2 = st.columns(2)
                    with d1:
                        if labour:
                            st.markdown("**Labour**")
                            for e in labour:
                                st.markdown(f"- {e['name']} | {e.get('trade', '—')} | {e['stated_total']}h")
                    with d2:
                        if plant:
                            st.markdown("**Plant**")
                            for e in plant:
                                st.markdown(f"- {e['name']} | {e['stated_total']}h")

# ── Cross-gang ────────────────────────────────────────────────────────────────
if len(all_parsed) > 1:
    st.markdown("""
    <div class="sc-gang">
        <span class="sc-gang-name">Cross-Gang Checks</span>
    </div>
    """, unsafe_allow_html=True)
    if not cross_issues:
        st.success("No cross-gang duplicates found.")
    else:
        for issue in cross_issues:
            render_issue(issue)
