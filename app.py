import streamlit as st
from collections import defaultdict
from parser import parse_pdf
from checks import run_day_checks, check_cross_gang_duplicates

st.set_page_config(page_title="SheetCheck", layout="wide", page_icon="🟠")

st.markdown("""
<style>
    /* Header */
    .sc-header { padding: 2rem 0 1rem 0; }
    .sc-logo   { font-size: 2rem; font-weight: 800; letter-spacing: -0.03em; color: #f59e0b; }
    .sc-tag    { font-size: 0.95rem; color: #94a3b8; margin-top: 0.25rem; }

    /* Upload section */
    .sc-upload-title {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #f59e0b;
        margin-bottom: 0.5rem;
    }

    /* Tighten Streamlit default padding */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 960px !important;
    }

    /* Summary metrics */
    .sc-summary {
        display: flex;
        gap: 1rem;
        margin: 1.5rem 0;
    }
    .sc-metric {
        background: #1c1f2e;
        border: 1px solid #2d3148;
        border-radius: 10px;
        padding: 1rem 1.5rem;
        flex: 1;
    }
    .sc-metric-val  { font-size: 2rem; font-weight: 700; line-height: 1; }
    .sc-metric-lbl  { font-size: 0.75rem; color: #94a3b8; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.07em; }
    .sc-red    { color: #ef4444; }
    .sc-amber  { color: #f59e0b; }
    .sc-green  { color: #22c55e; }

    /* Gang header */
    .sc-gang-header {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #f59e0b;
        border-bottom: 1px solid #2d3148;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 0.75rem 0;
    }

    /* Issue cards */
    .issue-error {
        background: #2d1515;
        border-left: 3px solid #ef4444;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 6px;
        font-size: 0.88rem;
        color: #fca5a5;
    }
    .issue-warning {
        background: #2d2010;
        border-left: 3px solid #f59e0b;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 6px;
        font-size: 0.88rem;
        color: #fcd34d;
    }
    .issue-label {
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        opacity: 0.7;
    }

    /* Hide default Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer     { visibility: hidden; }
    header     { visibility: hidden; }
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
    if issue["severity"] == "error":
        st.markdown(
            f'<div class="issue-error"><div class="issue-label">❌ {label}</div>{issue["message"]}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="issue-warning"><div class="issue-label">⚠️ {label}</div>{issue["message"]}</div>',
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


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="sc-header">
    <div class="sc-logo">SheetCheck</div>
    <div class="sc-tag">Catches errors in your daily allocation sheets before they're signed off.</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
st.markdown('<div class="sc-upload-title">Upload gang PDFs — one per gang</div>', unsafe_allow_html=True)

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

if not uploads:
    st.stop()

if not st.button("Run Checks →", type="primary", use_container_width=False):
    st.stop()

# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
all_parsed = {}
with st.spinner("Reading PDFs…"):
    for gang_label, pdf_file in uploads.items():
        all_parsed[gang_label] = parse_pdf(pdf_file)

# ---------------------------------------------------------------------------
# Run all checks once
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
st.markdown('<div class="sc-summary">', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)

with c1:
    colour = "sc-red" if total_errors else "sc-green"
    st.markdown(f"""
    <div class="sc-metric">
        <div class="sc-metric-val {colour}">{total_errors}</div>
        <div class="sc-metric-lbl">Errors</div>
    </div>""", unsafe_allow_html=True)

with c2:
    colour = "sc-amber" if total_warnings else "sc-green"
    st.markdown(f"""
    <div class="sc-metric">
        <div class="sc-metric-val {colour}">{total_warnings}</div>
        <div class="sc-metric-lbl">Warnings</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="sc-metric">
        <div class="sc-metric-val" style="color:#e2e8f0">{total_days}</div>
        <div class="sc-metric-lbl">{len(uploads)} Gang{'s' if len(uploads) > 1 else ''} · {total_days} Day{'s' if total_days > 1 else ''} checked</div>
    </div>""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

if total_errors == 0 and total_warnings == 0:
    st.success("All checks passed across every sheet.")

# ---------------------------------------------------------------------------
# Per-gang results
# ---------------------------------------------------------------------------
for gang_label, results in all_results.items():
    st.markdown(f'<div class="sc-gang-header">{gang_label} — {uploads[gang_label].name}</div>', unsafe_allow_html=True)

    for day_data, issues in results:
        errors   = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        label    = f"{day_label(day_data)}  —  {issue_badge(issues)}"

        with st.expander(label, expanded=bool(issues)):
            if not issues:
                st.markdown('<span style="color:#22c55e">No issues found.</span>', unsafe_allow_html=True)
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

# ---------------------------------------------------------------------------
# Cross-gang results
# ---------------------------------------------------------------------------
if len(all_parsed) > 1:
    st.markdown('<div class="sc-gang-header">Cross-Gang Checks</div>', unsafe_allow_html=True)
    if not cross_issues:
        st.success("No cross-gang duplicates found.")
    else:
        for issue in cross_issues:
            render_issue(issue)
