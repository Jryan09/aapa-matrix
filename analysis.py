"""Analysis engine: turns each department's raw output into the Matrix 1C columns.

Quantitative part : parse target / actual -> % accomplishment -> rating
Qualitative part  : keyword theme coding of the narrative remarks (English + Filipino)
Drafting          : Issues/Concerns/Gaps and Recommendation/Intervention text
Optional          : Claude API polish (only if ANTHROPIC_API_KEY is set)
"""
import os
import re
from collections import Counter

# ----------------------------------------------------------------- themes ---
THEMES = {
    "Funding / Budget": (
        ["fund", "budget", "allotment", "pondo", "salapi", "kulang sa pondo", "financial", "cash", "payment",
         "unpaid", "delayed release", "insufficient fund", "no fund", "limited fund"],
        "Prioritize the activity in the next AIP/budget cycle and identify supplemental or alternative funding "
        "(e.g. Supplemental Budget, 20% Development Fund, grants).",
    ),
    "Manpower / Staffing": (
        ["manpower", "staff", "personnel", "tauhan", "kulang ang tao", "understaffed", "vacant", "vacancy",
         "plantilla", "overtime", "workload", "resign", "job order", "contract of service"],
        "Fill vacant positions or augment through job order/COS personnel; redistribute workload and cross-train staff.",
    ),
    "Equipment / Logistics": (
        ["equipment", "vehicle", "truck", "backhoe", "machine", "tools", "supplies", "materials", "logistic",
         "sasakyan", "kagamitan", "breakdown", "broken", "repair", "fuel", "gasolina", "maintenance of"],
        "Procure, repair or schedule preventive maintenance of equipment and vehicles; ensure supplies are stocked ahead of time.",
    ),
    "Delays / Procurement": (
        ["procurement", "bidding", "bid", "failed bidding", "delay", "late submission", "huli",
         "pending", "awaiting", "waiting", "not yet", "backlog", "extension", "suspended"],
        "Address the delays: start procurement and approvals early (align with the Annual Procurement Plan), monitor "
        "milestones monthly and resolve bottlenecks with the offices concerned (e.g. BAC/GSO, approving authorities).",
    ),
    "Weather / Calamity": (
        ["typhoon", "flood", "rain", "weather", "calamity", "disaster", "bagyo", "baha", "el nino", "drought",
         "storm", "landslide", "earthquake"],
        "Build contingency schedules for weather and calamity risks; coordinate with MDRRMO and re-program affected activities.",
    ),
    "Coordination / Stakeholders": (
        ["coordination", "coordinate", "stakeholder", "partner", "barangay", "agency", "dpwh", "denr", "dilg",
         "lgu", "cooperation", "participation", "attendance", "buy-in", "conflict", "right of way"],
        "Strengthen coordination with partner offices, barangays and agencies through regular meetings and clear MOAs.",
    ),
    "Technology / Data": (
        ["internet", "system", "software", "computer", "online", "data", "database", "connectivity", "network",
         "signal", "digital", "encoding", "records"],
        "Upgrade systems and connectivity, standardize data/records management and train users on the tools.",
    ),
    "Policy / Legal": (
        ["policy", "ordinance", "legal", "permit", "clearance", "regulation", "compliance", "audit",
         "coa", "resolution", "approval", "guideline", "circular", "title", "titling"],
        "Expedite the issuance/approval of needed ordinances, permits and clearances and align the activity with current guidelines.",
    ),
    "Capacity / Training": (
        ["training", "capacity", "skills", "competency", "orientation", "seminar", "knowledge", "awareness",
         "kakayahan", "trained", "technical assistance"],
        "Conduct targeted capacity-building and technical assistance for the personnel and stakeholders involved.",
    ),
    "Demand / Community": (
        ["beneficiar", "community", "resident", "request", "demand", "complaint", "mamamayan", "constituent",
         "informal settler", "turnout", "response of"],
        "Intensify information drives and community engagement; validate the beneficiary list and demand before programming.",
    ),
}

RATINGS = [
    (100, "Fully accomplished"),
    (80, "Substantially accomplished"),
    (50, "Partially accomplished"),
    (0, "Not accomplished / Critical"),
]

DONE_WORDS = ("completed", "complete", "done", "accomplished", "fully", "achieved", "tapos", "natapos", "yes")
PART_WORDS = ("ongoing", "on-going", "in progress", "partial", "partially", "ongoing", "ginagawa")
NONE_WORDS = ("not started", "none", "no accomplishment", "wala", "not done", "zero", "cancelled", "canceled")


# ------------------------------------------------------------- numbers -----
def _first_number(text):
    """Return (value, is_percent) for the first number found, else (None, False)."""
    if text is None:
        return None, False
    s = str(text).replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(%|percent|pct)?", s, re.IGNORECASE)
    if not m:
        return None, False
    return float(m.group(1)), bool(m.group(2))


def accomplishment_rate(target, actual):
    """% of accomplishment, or None when it cannot be quantified."""
    t, _ = _first_number(target)
    a, _ = _first_number(actual)
    if t is not None and a is not None:
        if t == 0:
            return 100.0 if a == 0 else None
        return round(a / t * 100, 1)
    low = str(actual or "").strip().lower()
    if not low:
        return None
    if any(w in low for w in NONE_WORDS):
        return 0.0
    if any(w in low for w in DONE_WORDS):
        return 100.0
    if any(w in low for w in PART_WORDS):
        return 50.0
    return None


def rating_for(rate):
    if rate is None:
        return "Not rated"
    for cut, label in RATINGS:
        if rate >= cut:
            return label
    return RATINGS[-1][1]


# -------------------------------------------------------------- themes -----
def _kw_hit(low, kw):
    # prefix word-boundary: "fund" matches "funding" but "rain" does not match "training"
    return re.search(r"(?<![a-z0-9])" + re.escape(kw.strip()), low) is not None


def code_themes(text):
    """Return the list of themes whose keywords occur in text (keeps dictionary order)."""
    low = re.sub(r"\s+", " ", str(text or "").lower())
    return [name for name, (kws, _) in THEMES.items() if any(_kw_hit(low, k) for k in kws)]


def _clean(text, limit=450):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def _fmt(n):
    return f"{n:,.2f}".rstrip("0").rstrip(".")


# -------------------------------------------------------------- drafting ---
def analyze_row(row):
    """row: dict with target, actual, remarks. Returns dict with rate, rating, themes, issues, reco."""
    target, actual, remarks = row.get("target"), row.get("actual"), row.get("remarks")
    rate = accomplishment_rate(target, actual)
    rating = rating_for(rate)
    themes = code_themes(remarks)
    note = _clean(remarks)

    t, _ = _first_number(target)
    a, _ = _first_number(actual)
    parts = []
    if rate is None:
        parts.append("Accomplishment could not be quantified from the data submitted.")
    else:
        line = f"{_fmt(rate)}% of target accomplished ({rating})."
        if t is not None and a is not None and rate < 100:
            line += f" Gap of {_fmt(t - a)} against the target of {_fmt(t)}."
        elif rate > 100:
            line += " Target was exceeded."
        parts.append(line)
    if note:
        parts.append(f"Concerns reported: {note}")
    elif rate is not None and rate < 100:
        parts.append("No explanation for the gap was submitted.")
    elif rate is not None:
        parts.append("No issues or concerns reported.")
    if themes:
        parts.append("Main factors: " + ", ".join(themes) + ".")
    issues = " ".join(parts)

    recos = []
    for th in themes:
        recos.append(THEMES[th][1])
    if rate is None:
        recos.append("Submit measurable target and actual figures so performance can be assessed.")
    elif rate >= 100:
        recos.append("Sustain the performance and consider a higher target in the next planning cycle.")
    elif not themes:
        recos.append("Conduct a root-cause review of the gap and submit a catch-up plan with timelines.")
    if rate is not None and rate < 50:
        recos.insert(0, "Priority attention: prepare a recovery plan with monthly monitoring by the Department Head.")
    reco = " ".join(f"({i}) {r}" for i, r in enumerate(recos, 1)) if len(recos) > 1 else (recos[0] if recos else "")

    return {"rate": rate, "rating": rating, "themes": themes, "issues": issues, "reco": reco}


def analyze_all(rows):
    """rows: list of dicts. Adds analysis keys to a copy of each row."""
    out = []
    for r in rows:
        d = dict(r)
        d.update(analyze_row(r))
        out.append(d)
    return out


def summarize(rows):
    """Cross-department summary from analyzed rows."""
    by_dept, themes = {}, Counter()
    for r in rows:
        dep = r.get("department") or "(no department)"
        s = by_dept.setdefault(dep, {"indicators": 0, "rated": 0, "sum": 0.0, "met": 0})
        s["indicators"] += 1
        if r.get("rate") is not None:
            s["rated"] += 1
            s["sum"] += min(r["rate"], 100)
            s["met"] += 1 if r["rate"] >= 100 else 0
        for th in r.get("themes", []):
            themes[(dep, th)] += 1
    table = []
    for dep, s in by_dept.items():
        table.append({"Department": dep, "Indicators": s["indicators"], "Rated": s["rated"],
                      "Targets met": s["met"],
                      "Avg accomplishment %": round(s["sum"] / s["rated"], 1) if s["rated"] else None})
    overall = Counter()
    for (_, th), n in themes.items():
        overall[th] += n
    return table, overall


# --------------------------------------------------------- optional AI -----
def ai_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ai_polish(row, issues, reco, model="claude-sonnet-5-5"):
    """Rewrite the drafted issues/recommendation in clear formal language. Returns (issues, reco).
    Falls back to the drafted text on any error."""
    try:
        import anthropic  # optional dependency
        client = anthropic.Anthropic()
        prompt = (
            "You help a Philippine LGU prepare the AAPA Matrix 1C (Development Objectives). "
            "Rewrite the two cells below in clear, formal, concise English. Keep every fact and number; "
            "do not invent data. Reply exactly in this format:\nISSUES: <text>\nRECOMMENDATION: <text>\n\n"
            f"Result: {row.get('result')}\nIndicator: {row.get('indicator')}\n"
            f"Target: {row.get('target')}\nActual: {row.get('actual')}\n"
            f"Department's own remarks: {row.get('remarks')}\n\n"
            f"Draft issues: {issues}\nDraft recommendation: {reco}"
        )
        msg = client.messages.create(model=model, max_tokens=700, messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"ISSUES:\s*(.*?)\s*RECOMMENDATION:\s*(.*)", text, re.S)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    except Exception:
        pass
    return issues, reco
