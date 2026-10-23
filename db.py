"""Tiny SQLite store shared by all departments using the deployed app."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("AAPA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "aapa.db"))

FIELDS = ["year", "department", "sector", "mfo", "outcome", "result", "indicator", "target", "actual",
          "remarks", "issues_final", "reco_final"]


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER, department TEXT, sector TEXT, mfo TEXT, outcome TEXT,
            result TEXT, indicator TEXT, target TEXT, actual TEXT, remarks TEXT,
            issues_final TEXT, reco_final TEXT,
            created TEXT DEFAULT CURRENT_TIMESTAMP)""")


def add_rows(rows):
    """rows: list of dicts (keys in FIELDS). Returns number inserted."""
    n = 0
    with conn() as c:
        for r in rows:
            vals = [r.get(f) for f in FIELDS]
            if not any(str(r.get(f) or "").strip() for f in ("result", "indicator", "target", "actual")):
                continue
            c.execute(f"INSERT INTO submissions({','.join(FIELDS)}) VALUES({','.join('?' * len(FIELDS))})", vals)
            n += 1
    return n


def fetch(year=None, department=None):
    q, args = "SELECT * FROM submissions WHERE 1=1", []
    if year:
        q += " AND year=?"
        args.append(int(year))
    if department:
        q += " AND department=?"
        args.append(department)
    q += " ORDER BY department, id"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def departments(year=None):
    with conn() as c:
        if year:
            cur = c.execute("SELECT DISTINCT department FROM submissions WHERE year=? ORDER BY 1", (int(year),))
        else:
            cur = c.execute("SELECT DISTINCT department FROM submissions ORDER BY 1")
        return [r[0] for r in cur.fetchall() if r[0]]


def years():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT year FROM submissions ORDER BY 1 DESC").fetchall() if r[0]]


def update_final(row_id, issues_final, reco_final):
    with conn() as c:
        c.execute("UPDATE submissions SET issues_final=?, reco_final=? WHERE id=?", (issues_final, reco_final, int(row_id)))


def update_inputs(row_id, **kw):
    cols = [k for k in kw if k in FIELDS]
    if not cols:
        return
    with conn() as c:
        c.execute(f"UPDATE submissions SET {','.join(k + '=?' for k in cols)} WHERE id=?",
                  [kw[k] for k in cols] + [int(row_id)])


def delete(row_id):
    with conn() as c:
        c.execute("DELETE FROM submissions WHERE id=?", (int(row_id),))
