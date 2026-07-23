"""Read-only access to data/legacy.db, plus natural-language patient resolution.

The connection is opened in SQLite's URI mode=ro -- a hard guarantee against
any write path existing, not just an absence of INSERT/UPDATE statements.
"""
import difflib
import os
import re
import sqlite3
from pathlib import Path

from mcp_server.datetimes import epoch_to_yyyymmdd, mmddyyyy_to_yyyymmdd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "legacy.db")

_MRN_PATTERN = re.compile(r"MRN\d+", re.IGNORECASE)

_QUERY_STOPWORDS = {
    "show", "me", "find", "get", "look", "lookup", "up", "patient", "patients",
    "record", "records", "for", "of", "the", "a", "an", "what", "whats", "is",
    "are", "condition", "conditions", "history", "demographics", "info",
    "information", "about", "please", "can", "you", "tell", "give", "s",
}


def get_connection():
    uri = Path(DB_PATH).absolute().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _strip_trailing_digits(name):
    """Synthea appends disambiguating digits to names (e.g. 'Ben667') --
    strip them for matching purposes only; the stored value is untouched."""
    return re.sub(r"\d+$", "", name or "").strip().lower()


def _extract_mrn(query):
    m = _MRN_PATTERN.search(query.upper())
    return m.group(0) if m else None


def _extract_name_tokens(query):
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", query)
    tokens = [t.lower() for t in cleaned.split()]
    return [t for t in tokens if t not in _QUERY_STOPWORDS]


def _score_identity(query_tokens, first_name, last_name):
    norm_first = _strip_trailing_digits(first_name)
    norm_last = _strip_trailing_digits(last_name)
    query_joined = " ".join(query_tokens)
    candidate_joined = f"{norm_first} {norm_last}".strip()
    ratio = difflib.SequenceMatcher(None, query_joined, candidate_joined).ratio()
    exact_token_hits = sum(1 for t in query_tokens if t in (norm_first, norm_last))
    if exact_token_hits:
        ratio = max(ratio, 0.5 + 0.25 * exact_token_hits)
    return ratio


def resolve_patient(conn, query):
    """Returns a list of matching patient_identity rows for a natural-language query.

    Empty list = no confident match. More than one row = ambiguous match --
    the caller must not guess a single one; return all of them with a flag.
    """
    mrn = _extract_mrn(query)
    if mrn:
        row = conn.execute("SELECT * FROM patient_identity WHERE mrn = ?", (mrn,)).fetchone()
        return [row] if row else []

    tokens = _extract_name_tokens(query)
    if not tokens:
        return []

    rows = conn.execute("SELECT * FROM patient_identity").fetchall()
    scored = [(_score_identity(tokens, r["first_name"], r["last_name"]), r) for r in rows]
    scored.sort(key=lambda pair: -pair[0])

    if not scored or scored[0][0] < 0.5:
        return []

    best_score = scored[0][0]
    return [r for score, r in scored if score >= best_score - 0.15 and score >= 0.5]


def find_contact_for_identity(conn, identity_row):
    """Ticket 2 join rule: normalized full_name + matching DOB, no shared key.

    Returns (contact_row, ambiguous). ambiguous is True on zero or multiple
    matches -- per Ticket 2's fallback rule, the caller must not guess.
    """
    target_full_name = f"{identity_row['last_name']}, {identity_row['first_name']}".strip().lower()
    target_yyyymmdd = mmddyyyy_to_yyyymmdd(identity_row["dob_mmddyyyy"])

    matches = []
    for row in conn.execute("SELECT * FROM patient_contact"):
        if row["full_name"].strip().lower() != target_full_name:
            continue
        if epoch_to_yyyymmdd(row["dob_epoch"]) != target_yyyymmdd:
            continue
        matches.append(row)

    if len(matches) == 1:
        return matches[0], False
    return None, True


def get_conditions(conn, mrn):
    return conn.execute("SELECT * FROM conditions_log WHERE mrn = ?", (mrn,)).fetchall()


def get_vitals(conn, mrn):
    return conn.execute("SELECT * FROM vitals_log WHERE mrn = ?", (mrn,)).fetchall()


# Clinical shorthand/synonyms -> normalized vital_label(s) they refer to.
# Matched against the raw query text so a request like "Ben Torp's BP" or
# "heart rate for MRN720072" narrows to the relevant vitals instead of
# returning everything the patient has on file.
_VITAL_KEYWORDS = {
    "systolic": {"systolic blood pressure"},
    "diastolic": {"diastolic blood pressure"},
    "blood pressure": {"systolic blood pressure", "diastolic blood pressure"},
    "bp": {"systolic blood pressure", "diastolic blood pressure"},
    "heart rate": {"heart rate"},
    "pulse": {"heart rate"},
    "weight-for-length": {"weight-for-length per age and sex"},
    "weight": {"body weight"},
    "height": {"body height"},
    "temperature": {"body temperature"},
    "temp": {"body temperature"},
    "respiratory rate": {"respiratory rate"},
    "respiration": {"respiratory rate"},
    "oxygen saturation": {"oxygen saturation in arterial blood"},
    "oxygen": {"oxygen saturation in arterial blood"},
    "o2 sat": {"oxygen saturation in arterial blood"},
    "spo2": {"oxygen saturation in arterial blood"},
    "body mass index": {"body mass index (bmi) [ratio]", "body mass index (bmi) [percentile] per age and sex"},
    "bmi": {"body mass index (bmi) [ratio]", "body mass index (bmi) [percentile] per age and sex"},
    "pain": {"pain severity - 0-10 verbal numeric rating [score] - reported"},
    "head circumference": {"head occipital-frontal circumference", "head occipital-frontal circumference percentile"},
    "occipital": {"head occipital-frontal circumference", "head occipital-frontal circumference percentile"},
    "intraocular pressure": {"left eye intraocular pressure", "right eye intraocular pressure"},
    "eye pressure": {"left eye intraocular pressure", "right eye intraocular pressure"},
}


def extract_vital_type_filter(query):
    """Returns a set of normalized vital_labels to restrict to, or None for
    'no specific vital type mentioned -- return everything on file'."""
    ql = query.lower()
    matched = set()
    for keyword, labels in _VITAL_KEYWORDS.items():
        if keyword in ql:
            matched |= labels
    return matched or None
