import base64
import streamlit as st
from collections import defaultdict
from parser import parse_pdf
from checks import run_day_checks, check_cross_gang_duplicates

st.set_page_config(page_title="SheetCheck", layout="wide", page_icon="🟠")

# Load hero image
with open("hero.jpg", "rb") as f:
    hero_b64 = base64.b64encode(f.read()).decode()

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* Remove Streamlit chrome */
    #MainMenu, footer, header {{ visibility: hidden; }}
    .block-container {{
        padding: 0 !important;
        max-width: 100% !important;
    }}

    /* ── Hero ── */
    .sc-hero {{
        background: linear-gradient(to bottom, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.72) 100%),
                    url("data:image/jpeg;base64,{hero_b64}") center center / cover no-repeat;
        padding: 80px 64px 64px;
        min-height: 320px;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }}
    .sc-hero-eyebrow {{
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #f59e0b;
        margin-bottom: 10px;
    }}
    .sc-hero-title {{
        font-size: 3rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.03em;
        line-height: 1;
        margin-bottom: 12px;
    }}
    .sc-hero-sub {{
        font-size: 1rem;
        color: rgba(255,255,255,0.65);
        max-width: 480px;
        line-height: 1.5;
    }}

    /* ── Upload section ── */
    .sc-body {{
        background: #0f1117;
        padding: 48px 64px;
    }}
    .sc-section-label {{
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #f59e0b;
        margin-bottom: 16px;
    }}

    /* Style native Streamlit file uploader to look like a card */
    [data-testid="stFileUploader"] {{
        background: #1a1d2e;
        border: 1px solid #2a2d40;
        border-radius: 12px;
        padding: 8px;
    }}
    [data-testid="stFileUploader"] label {{
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        background: transparent !important;
        border: 1.5px dashed #2a2d40 !important;
        border-radius: 8px !important;
    }}
    [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: #f59e0b !important;
        background: rgba(245,158,11,0.04) !important;
    }}

    /* Run button */
    div[data-testid="stButton"] > button[kind="primary"] {{
        background: #f59e0b !important;
        color: #000000 !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.6rem 2rem !important;
        letter-spacing: 0.02em;
        margin-top: 24px;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        background: #d97706 !important;
    }}

    /* ── Summary metrics ── */
    .sc-divider {{
        border: none;
        border-top: 1px solid #1e2130;
        margin: 0 64px;
    }}
    .sc-results {{
        background: #0f1117;
        padding: 40px 64px;
    }}
    .sc-metric-row {{
        display: flex;
        gap: 16px;
        margin-bottom: 40px;
    }}
    .sc-metric {{
        background: #1a1d2e;
        border: 1px solid #2a2d40;
        border-radius: 12px;
        padding: 20px 24px;
        flex: 1;
    }}
    .sc-metric-val  {{ font-size: 2.2rem; font-weight: 800; line-height: 1; letter-spacing: -0.03em; }}
    .sc-metric-lbl  {{ font-size: 0.7rem; color: #64748b; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }}
    .sc-red   {{ color: #ef4444; }}
    .sc-amber {{ color: #f59e0b; }}
    .sc-green {{ color: #22c55e; }}

    /* ── Gang section header ── */
    .sc-gang-header {{
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #f59e0b;
        border-bottom: 1px solid #1e2130;
        padding-bottom: 10px;
        margin: 36px 0 16px;
    }}

    /* ── Issue cards ── */
    .issue-error {{
        background: rgba(239,68,68,0.08);
        border-left: 3px solid #ef4444;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.875rem;
        color: #fca5a5;
        line-height: 1.5;
    }}
    .issue-warning {{
        background: rgba(245,158,11,0.08);
        border-left: 3px solid #f59e0b;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.875rem;
        color: #fcd34d;
        line-height: 1.5;
    }}
    .issue-label {{
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.65rem;
        letter-spacing: 0.1em;
        margin-bottom: 4px;
        opacity: 0.6;
    }}

    /* Streamlit expander styling */
    [data-testid="stExpander"] {{
        background: #1a1d2e !important;
        border: 1px solid #2a2d40 !important;
        border-radius: 10px !important;
        margin-bottom: 8px !important;
    }}
    [data-testid="stExpander"] summary {{
        font-weight: 500 !important;
        font-size: 0.9rem !important;
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
    cls = "issue-error" if issue["severity"] == "error" else "issue-warning"
    icon = "❌" if issue["severity"] == "error" else "⚠️"
    st.markdown(
        f'<div class="{cls}"><div class="issue-label">{icon} {label}</div>{issue["message"]}</div>',
        unsafe_allow_html=True,
    )


def day_label(day_data):
    day  = day_data.get("day") or f"Page {day_data.get('page', '?')}"
    date = day_data.get("date_str", "")
    return f"{day}  {date}".strip()


def issue_badge(issues):
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


# ── Hero ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="sc-hero">
    <div class="sc-hero-eyebrow">ACS Civils</div>
    <div class="sc-hero-title">SheetCheck</div>
    <div class="sc-hero-sub">Catches errors in your daily allocation sheets before they're signed off.</div>
</div>
""", unsafe_allow_html=True)

# ── Upload ───────────────────────────────────────────────────────────────────
st.markdown('<div class="sc-body">', unsafe_allow_html=True)
st.markdown('<div class="sc-section-label">Upload gang PDFs — one per gang</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
uploads = {}
with col1:
    f = st.file_uploader("Gang 1", type="pdf", key="gang1")
    if f:
        uploads["Gang 1"] = f
with col2:
    f = st.file_uploader("Gang 2", type="pdf", key="gang2")
    if f:
        uploads["Gang 2"] = f
with col3:
    f = st.file_uploader("Gang 3", type="pdf", key="gang3")
    if f:
        uploads["Gang 3"] = f

run = st.button("Run Checks →", type="primary", disabled=not uploads)
st.markdown('</div>', unsafe_allow_html=True)

if not uploads or not run:
    st.stop()

# ── Parse ────────────────────────────────────────────────────────────────────
all_parsed = {}
with st.spinner("Reading PDFs…"):
    for gang_label, pdf_file in uploads.items():
        all_parsed[gang_label] = parse_pdf(pdf_file)

# ── Run all checks once ───────────────────────────────────────────────────────
all_results = {}
for gang_label, days in all_parsed.items():
    all_results[gang_label] = [(d, run_day_checks(d)) for d in days]

days_by_date = defaultdict(list)
for gang_label, days in all_parsed.items():
    for day_data in days:
        date_key = day_data.get("date_str") or f"page_{day_data.get('page')}"
        days_by_date[date_key].append((gang_label, day_data))

cross_issues = []
if len(all_parsed) > 1:
    for date_key, gang_days in days_by_date.items():
        if len(gang_days) > 1:
            cross_issues += check_cross_gang_duplicates(gang_days)

all_issues_flat = [i for results in all_results.values() for _, issues in results for i in issues] + cross_issues
total_errors   = sum(1 for i in all_issues_flat if i["severity"] == "error")
total_warnings = sum(1 for i in all_issues_flat if i["severity"] == "warning")
total_days     = sum(len(r) for r in all_results.values())

# ── Results ───────────────────────────────────────────────────────────────────
st.markdown('<hr class="sc-divider">', unsafe_allow_html=True)
st.markdown('<div class="sc-results">', unsafe_allow_html=True)

# Summary metrics
err_colour  = "sc-red"   if total_errors   else "sc-green"
warn_colour = "sc-amber" if total_warnings else "sc-green"
st.markdown(f"""
<div class="sc-metric-row">
    <div class="sc-metric">
        <div class="sc-metric-val {err_colour}">{total_errors}</div>
        <div class="sc-metric-lbl">Errors</div>
    </div>
    <div class="sc-metric">
        <div class="sc-metric-val {warn_colour}">{total_warnings}</div>
        <div class="sc-metric-lbl">Warnings</div>
    </div>
    <div class="sc-metric">
        <div class="sc-metric-val" style="color:#e2e8f0">{total_days}</div>
        <div class="sc-metric-lbl">{len(uploads)} Gang{'s' if len(uploads) > 1 else ''} · {total_days} Day{'s' if total_days > 1 else ''} checked</div>
    </div>
</div>
""", unsafe_allow_html=True)

if total_errors == 0 and total_warnings == 0:
    st.success("All checks passed across every sheet.")

# Per-gang results
for gang_label, results in all_results.items():
    st.markdown(f'<div class="sc-gang-header">{gang_label} — {uploads[gang_label].name}</div>', unsafe_allow_html=True)

    for day_data, issues in results:
        errors   = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        label    = f"{day_label(day_data)}  —  {issue_badge(issues)}"

        with st.expander(label, expanded=bool(issues)):
            if not issues:
                st.markdown('<span style="color:#22c55e;font-size:0.875rem">No issues found.</span>', unsafe_allow_html=True)
            else:
                for issue in errors:
                    render_issue(issue)
                for issue in warnings:
                    render_issue(issue)

            labour = day_data.get("labour", [])
            plant  = day_data.get("plant",  [])
            if labour or plant:
                with st.expander("View parsed data", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        if labour:
                            st.markdown("**Labour**")
                            for e in labour:
                                st.markdown(f"- {e['name']} | {e.get('trade', '—')} | {e['stated_total']}h")
                    with c2:
                        if plant:
                            st.markdown("**Plant**")
                            for e in plant:
                                st.markdown(f"- {e['name']} | {e['stated_total']}h")

# Cross-gang
if len(all_parsed) > 1:
    st.markdown('<div class="sc-gang-header">Cross-Gang Checks</div>', unsafe_allow_html=True)
    if not cross_issues:
        st.success("No cross-gang duplicates found.")
    else:
        for issue in cross_issues:
            render_issue(issue)

st.markdown('</div>', unsafe_allow_html=True)
