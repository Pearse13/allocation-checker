import streamlit as st
from collections import defaultdict
from parser import parse_pdf
from checks import run_day_checks, check_cross_gang_duplicates

st.set_page_config(page_title="Allocation Checker", layout="wide", page_icon="📋")

st.markdown("""
<style>
    .issue-error {
        background: #ffeaea;
        border-left: 4px solid #d63031;
        padding: 10px 14px;
        border-radius: 4px;
        margin-bottom: 6px;
        font-size: 0.92rem;
    }
    .issue-warning {
        background: #fff8e6;
        border-left: 4px solid #e17055;
        padding: 10px 14px;
        border-radius: 4px;
        margin-bottom: 6px;
        font-size: 0.92rem;
    }
    .issue-label {
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        margin-bottom: 2px;
    }
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
        return "✅ All clear"
    parts = []
    if errors:
        parts.append(f"❌ {len(errors)} error{'s' if len(errors) > 1 else ''}")
    if warnings:
        parts.append(f"⚠️ {len(warnings)} warning{'s' if len(warnings) > 1 else ''}")
    return "  ".join(parts)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
st.title("📋 Allocation Sheet Checker")
st.caption("Upload 1–3 gang PDFs. Each PDF can cover a full week (multiple pages).")
st.divider()

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

if not st.button("Run Checks", type="primary"):
    st.stop()

# ---------------------------------------------------------------------------
# Parse all PDFs
# ---------------------------------------------------------------------------
all_parsed = {}
with st.spinner("Reading PDFs…"):
    for gang_label, pdf_file in uploads.items():
        all_parsed[gang_label] = parse_pdf(pdf_file)

# ---------------------------------------------------------------------------
# Run all checks once — store results alongside day data
# ---------------------------------------------------------------------------
all_results = {}  # gang_label -> list of (day_data, issues)
for gang_label, days in all_parsed.items():
    all_results[gang_label] = [(d, run_day_checks(d)) for d in days]

# Cross-gang checks
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

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
all_issues_flat = [i for results in all_results.values() for _, issues in results for i in issues] + cross_issues
total_errors   = sum(1 for i in all_issues_flat if i["severity"] == "error")
total_warnings = sum(1 for i in all_issues_flat if i["severity"] == "warning")
total_days     = sum(len(r) for r in all_results.values())

st.divider()
if total_errors == 0 and total_warnings == 0:
    st.success(f"### ✅ All checks passed — {len(uploads)} gang{'s' if len(uploads) > 1 else ''}, {total_days} day{'s' if total_days > 1 else ''}")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Errors",   total_errors)
    c2.metric("Warnings", total_warnings)
    c3.metric("Sheets checked", f"{len(uploads)} gang{'s' if len(uploads) > 1 else ''} · {total_days} day{'s' if total_days > 1 else ''}")

# ---------------------------------------------------------------------------
# Per-gang results
# ---------------------------------------------------------------------------
for gang_label, results in all_results.items():
    st.divider()
    st.markdown(f"### {gang_label} — {uploads[gang_label].name}")

    for day_data, issues in results:
        errors   = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        label    = f"{day_label(day_data)}  —  {issue_badge(issues)}"

        with st.expander(label, expanded=bool(issues)):
            if not issues:
                st.markdown("No issues found.")
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
    st.divider()
    st.markdown("### Cross-Gang Checks")
    if not cross_issues:
        st.success("No cross-gang duplicates found.")
    else:
        for issue in cross_issues:
            render_issue(issue)
