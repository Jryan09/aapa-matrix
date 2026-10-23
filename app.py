"""
AAPA Matrix 1C Analysis System  (Streamlit)

Departments submit their outputs -> the system analyzes them (targets vs actuals + themes in their
remarks) -> it drafts Issues/Concerns/Gaps and Recommendations -> exports Matrix 1C in the official layout.

Run locally:   streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

import analysis
import db
import ingest
import matrix1c

st.set_page_config(page_title="AAPA Matrix 1C Analysis", page_icon="📊", layout="wide")
db.init()

THIS_YEAR = 2026
PY_DEFAULT = 2025


def secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name)


# ------------------------------------------------------------- admin gate ---
def admin_ok(where):
    """Departments can submit freely. Analysis/exports can be protected with ADMIN_PASSWORD."""
    pw = secret("ADMIN_PASSWORD")
    if not pw:
        return True
    if st.session_state.get("admin"):
        return True
    with st.form(f"login_{where}"):
        entered = st.text_input("Admin password", type="password", key=f"pw_{where}")
        if st.form_submit_button("Unlock") and entered == pw:
            st.session_state["admin"] = True
            st.rerun()
    st.info("This section is for the planning/admin office. Enter the admin password.")
    return False


# ---------------------------------------------------------- submit data -----
def tab_submit():
    st.subheader("Submit department data")
    st.caption("Each department sends its outputs here. Choose the way that is easiest for you.")
    year = st.number_input("Performance Year (PY)", 2020, THIS_YEAR + 1, PY_DEFAULT, key="sub_year")
    method = st.radio("How do you want to submit?",
                      ["Fill in a form", "Upload a filled Matrix 1C (.xlsx)", "Upload the simple input table (.xlsx/.csv)"])

    if method == "Fill in a form":
        c1, c2 = st.columns(2)
        dept = c1.text_input("Department / Office", placeholder="e.g. MEO - Engineering")
        sector = c2.text_input("Sector", placeholder="e.g. Infrastructure")
        mfo = c1.text_input("Major Final Output")
        outcome = c2.text_input("Organizational Outcome")
        st.markdown("**Outputs / indicators** (add one row per indicator)")
        base = pd.DataFrame([{"Result": "", "Performance Indicator": "", "Target": "", "Actual": "", "Remarks / Challenges": ""}])
        edited = st.data_editor(base, num_rows="dynamic", hide_index=True, key="form_rows",
                                column_config={"Remarks / Challenges": st.column_config.TextColumn(width="large")})
        if st.button("Submit", type="primary"):
            if not dept.strip():
                st.error("Please enter the Department / Office.")
            else:
                rows = [{"year": int(year), "department": dept.strip(), "sector": sector.strip(), "mfo": mfo.strip(),
                         "outcome": outcome.strip(), "result": str(r["Result"] or ""),
                         "indicator": str(r["Performance Indicator"] or ""), "target": str(r["Target"] or ""),
                         "actual": str(r["Actual"] or ""), "remarks": str(r["Remarks / Challenges"] or "")}
                        for _, r in edited.iterrows()]
                n = db.add_rows(rows)
                st.success(f"Saved {n} indicator(s) for {dept.strip()}.") if n else st.warning("Nothing to save: the table is empty.")

    elif method.startswith("Upload a filled"):
        f = st.file_uploader("Filled Matrix 1C", type=["xlsx"], key="up1c")
        dept_override = st.text_input("Department name (only if the file's Department/Office cell is empty)")
        if f is not None and st.button("Import", type="primary"):
            try:
                meta, rows, file_year = ingest.read_matrix_1c(f)
                meta["department"] = meta.get("department") or dept_override.strip()
                if not meta["department"]:
                    st.error("The file has no Department/Office. Type the department name above and try again.")
                else:
                    for r in rows:
                        r.update(year=file_year or int(year), department=meta["department"], sector=meta.get("sector", ""),
                                 mfo=meta.get("mfo", ""), outcome=meta.get("outcome", ""))
                    st.success(f"Imported {db.add_rows(rows)} indicator(s) for {meta['department']} (PY {file_year or year}).")
            except Exception as e:
                st.error(f"Could not read the file: {e}")

    else:
        st.download_button("⬇ Download the input template", ingest.input_template_bytes(), "AAPA_input_template.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        f = st.file_uploader("Filled input table", type=["xlsx", "csv"], key="uptbl")
        dept_override = st.text_input("Department name (only if the file has no Department column)")
        if f is not None and st.button("Import table", type="primary"):
            try:
                rows = ingest.read_table(f, f.name)
                for r in rows:
                    r["department"] = r.get("department") or dept_override.strip()
                    r["year"] = int(year)
                if any(not r["department"] for r in rows):
                    st.error("Some rows have no department. Add a Department column or type the name above.")
                else:
                    st.success(f"Imported {db.add_rows(rows)} indicator(s).")
            except Exception as e:
                st.error(f"Could not read the file: {e}")


# --------------------------------------------------------- submissions ------
def tab_submissions():
    st.subheader("Submitted data")
    yrs = db.years()
    if not yrs:
        st.info("No submissions yet.")
        return
    year = st.selectbox("Performance Year", yrs, key="subs_year")
    rows = db.fetch(year=year)
    df = pd.DataFrame(rows)[["id", "department", "result", "indicator", "target", "actual", "remarks"]]
    st.dataframe(df, hide_index=True)
    st.markdown("**Delete a submission row**")
    c1, c2 = st.columns([1, 3])
    rid = c1.number_input("Row id", min_value=0, step=1, value=0)
    if c2.button("Delete row") and rid:
        db.delete(rid)
        st.rerun()


# ------------------------------------------------------------ analysis ------
def load_analyzed(year, depts):
    rows = [r for r in db.fetch(year=year) if not depts or r["department"] in depts]
    analyzed = analysis.analyze_all(rows)
    for r in analyzed:
        r["issues_show"] = r["issues_final"] or r["issues"]
        r["reco_show"] = r["reco_final"] or r["reco"]
    return analyzed


def tab_matrix():
    st.subheader("Analysis → Matrix 1C")
    yrs = db.years()
    if not yrs:
        st.info("No submissions yet.")
        return
    c1, c2 = st.columns([1, 3])
    year = c1.selectbox("Performance Year", yrs, key="mx_year")
    depts = c2.multiselect("Departments (leave empty for all)", db.departments(year))
    data = load_analyzed(year, depts)
    if not data:
        st.info("No data for this selection.")
        return

    st.caption("The **Issues** and **Recommendation** columns are drafted from each department's targets, actuals and remarks. "
               "You can edit them before exporting.")
    view = pd.DataFrame([{
        "id": r["id"], "Department": r["department"], "Results": r["result"], "Performance Indicators": r["indicator"],
        "Target": r["target"], "Actual": r["actual"],
        "% Accomplished": r["rate"], "Rating": r["rating"],
        "Issues/Concerns/Gaps": r["issues_show"], "Recommendation / Intervention": r["reco_show"]} for r in data])
    edited = st.data_editor(
        view, hide_index=True, key=f"mx_edit_{year}_{'|'.join(depts)}",
        disabled=["id", "Department", "Results", "Performance Indicators", "Target", "Actual", "% Accomplished", "Rating"],
        column_config={"Issues/Concerns/Gaps": st.column_config.TextColumn(width="large"),
                       "Recommendation / Intervention": st.column_config.TextColumn(width="large"),
                       "% Accomplished": st.column_config.NumberColumn(format="%.1f")})

    b1, b2, b3 = st.columns(3)
    if b1.button("💾 Save my edits"):
        gen = {r["id"]: r for r in data}
        for _, e in edited.iterrows():
            g = gen[int(e["id"])]
            db.update_final(e["id"],
                            "" if e["Issues/Concerns/Gaps"] == g["issues"] else e["Issues/Concerns/Gaps"],
                            "" if e["Recommendation / Intervention"] == g["reco"] else e["Recommendation / Intervention"])
        st.success("Saved.")
        st.rerun()
    if analysis.ai_available():
        if b2.button("✨ Polish wording with Claude"):
            with st.spinner("Rewriting..."):
                for r in data:
                    i2, r2 = analysis.ai_polish(r, r["issues_show"], r["reco_show"])
                    db.update_final(r["id"], i2, r2)
            st.rerun()
    else:
        b2.caption("Optional: set ANTHROPIC_API_KEY to enable AI wording polish.")

    # build export from what is currently on screen (edited values win)
    groups, order = {}, []
    for _, e in edited.iterrows():
        r = next(x for x in data if x["id"] == int(e["id"]))
        g = groups.get(r["department"])
        if g is None:
            g = groups[r["department"]] = {"meta": {"department": r["department"]}, "rows": []}
            order.append(r["department"])
        for k in ("sector", "mfo", "outcome"):
            if not g["meta"].get(k) and r.get(k):
                g["meta"][k] = r[k]
        g["rows"].append({"result": r["result"], "indicator": r["indicator"], "target": r["target"], "actual": r["actual"],
                          "issues": e["Issues/Concerns/Gaps"], "reco": e["Recommendation / Intervention"]})
    xlsx = matrix1c.build_workbook([groups[d] for d in order], year)
    b3.download_button("⬇ Download Matrix 1C (.xlsx)", xlsx, f"AAPA_Matrix_1C_PY{year}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    st.caption("The Excel file has one sheet per department in the official Matrix 1C layout.")


# ------------------------------------------------------------- summary ------
def tab_summary():
    st.subheader("Cross-department summary")
    yrs = db.years()
    if not yrs:
        st.info("No submissions yet.")
        return
    year = st.selectbox("Performance Year", yrs, key="sum_year")
    data = load_analyzed(year, [])
    table, themes = analysis.summarize(data)
    df = pd.DataFrame(table)
    st.dataframe(df, hide_index=True)
    if df["Avg accomplishment %"].notna().any():
        st.markdown("**Average accomplishment by department (%)**")
        st.bar_chart(df.set_index("Department")["Avg accomplishment %"])
    if themes:
        st.markdown("**Most common issues across all departments**")
        tdf = pd.DataFrame(themes.most_common(), columns=["Theme", "Mentions"])
        st.bar_chart(tdf.set_index("Theme"))
        for th, n in themes.most_common(3):
            who = sorted({r["department"] for r in data if th in r["themes"]})
            st.markdown(f"- **{th}** ({n} mentions) — {', '.join(who)}")
    low = [r for r in data if r["rate"] is not None and r["rate"] < 50]
    if low:
        st.markdown("**Indicators needing priority attention (below 50%)**")
        st.dataframe(pd.DataFrame([{"Department": r["department"], "Indicator": r["indicator"],
                                    "Target": r["target"], "Actual": r["actual"], "%": r["rate"]} for r in low]),
                     hide_index=True)


# ---------------------------------------------------------------- main ------
def main():
    st.title("📊 AAPA Matrix 1C — Qualitative Analysis System")
    st.caption("Municipality of Pinamalayan · Development Objectives per office mandate")
    t1, t2, t3, t4 = st.tabs(["1 · Submit data", "2 · Submitted data", "3 · Analysis → Matrix 1C", "4 · Summary"])
    with t1:
        tab_submit()
    with t2:
        if admin_ok("subs"):
            tab_submissions()
    with t3:
        if admin_ok("matrix"):
            tab_matrix()
    with t4:
        if admin_ok("summary"):
            tab_summary()


main()
