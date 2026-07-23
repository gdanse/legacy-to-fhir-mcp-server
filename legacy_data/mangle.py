"""Degrades clean extracted records into deliberately legacy-looking shapes.

Fixed seed so the mess is reproducible across runs, not different every time.
"""
import hashlib
import random
from datetime import datetime, timezone

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Common SNOMED display text -> messier free-text phrasing a human clerk
# might have typed instead of picking a coded value.
_CONDITION_REWRITES = {
    "Hypertension": "high blood pressure, on meds",
    "Essential hypertension (disorder)": "high blood pressure, on meds",
    "Diabetes": "diabetic",
    "Prediabetes": "borderline diabetic",
    "Anemia (disorder)": "anemic",
    "Major depressive disorder (disorder)": "depression, being managed",
    "Chronic sinusitis (disorder)": "chronic sinus issues",
    "Acute bronchitis (disorder)": "bad cough/bronchitis",
    "Osteoarthritis of knee": "bad knee, arthritis",
    "Body mass index 30+ - obesity (finding)": "overweight",
}


def _rng_for(patient_id):
    """Deterministic per-patient RNG so re-running the build is stable."""
    seed = int(hashlib.md5(patient_id.encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def make_mrn(patient_id):
    n = int(hashlib.md5(patient_id.encode()).hexdigest(), 16) % 900000 + 100000
    return f"MRN{n}"


def to_mmddyyyy(iso_date):
    """'1954-10-30' -> '10/30/1954'"""
    y, m, d = iso_date.split("-")
    return f"{m}/{d}/{y}"


def to_epoch(iso_date):
    """'1954-10-30' -> unix timestamp (midnight UTC)"""
    dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def to_yyyymmdd(iso_datetime):
    """'2008-02-28T16:21:36-07:00' -> '20080228'"""
    date_part = iso_datetime.split("T")[0]
    return date_part.replace("-", "")


def to_dd_mon_yyyy(iso_datetime):
    """'1972-12-23T12:15:42-07:00' -> '23-Dec-1972'"""
    date_part = iso_datetime.split("T")[0]
    y, m, d = date_part.split("-")
    return f"{d}-{_MONTHS[int(m) - 1]}-{y}"


def mangle_patient_identity(patient):
    return {
        "mrn": make_mrn(patient["id"]),
        "first_name": patient["first_name"],
        "last_name": patient["last_name"],
        "gender_code": {"male": "M", "female": "F"}.get(patient["gender"], "U"),
        "dob_mmddyyyy": to_mmddyyyy(patient["birth_date"]),
    }


def mangle_patient_contact(patient):
    return {
        "full_name": f"{patient['last_name']}, {patient['first_name']}",
        "dob_epoch": to_epoch(patient["birth_date"]),
        "ssn": patient["ssn"],
        "phone": patient["phone"],
        "address_line": patient["address_line"],
        "city": patient["city"],
        "state": patient["state"],
    }


def mangle_vitals(patient_id, mrn, vitals):
    rng = _rng_for(patient_id)
    rows = []
    for v in vitals:
        if not v["effective_datetime"]:
            continue
        label = v["label"]
        # Inconsistent naming/casing, same way different clerks/systems would type it.
        style = rng.random()
        if style < 0.3:
            label = label.upper()
        elif style < 0.5:
            label = label.lower()

        drop_unit = rng.random() < 0.35
        embed_unit_in_value = (not drop_unit) and "weight" in v["label"].lower() and rng.random() < 0.5

        if embed_unit_in_value:
            value_raw = f"{v['value']} {v['unit']}"
            unit = None
        elif drop_unit:
            value_raw = str(v["value"])
            unit = None
        else:
            value_raw = str(v["value"])
            unit = v["unit"]

        rows.append({
            "mrn": mrn,
            "vital_label": label,
            "value_raw": value_raw,
            "unit": unit,
            "recorded_date_yyyymmdd": to_yyyymmdd(v["effective_datetime"]),
        })
    return rows


def mangle_conditions(patient_id, mrn, conditions):
    rng = _rng_for(patient_id)
    rows = []
    # Group same-day conditions so some rows become one denormalized,
    # comma-separated free-text note instead of one row per coded condition.
    by_date = {}
    for c in conditions:
        if not c["onset_datetime"]:
            continue
        by_date.setdefault(c["onset_datetime"], []).append(c["text"])

    for onset_datetime, texts in by_date.items():
        phrases = [_CONDITION_REWRITES.get(t, t.replace(" (disorder)", "").replace(" (finding)", "")
                                              .replace(" (situation)", "").lower())
                   for t in texts]
        if len(phrases) > 1 and rng.random() < 0.5:
            note_text = ", ".join(phrases)
            rows.append({
                "mrn": mrn,
                "note_text": note_text,
                "onset_date_raw": to_dd_mon_yyyy(onset_datetime),
            })
        else:
            for phrase in phrases:
                rows.append({
                    "mrn": mrn,
                    "note_text": phrase,
                    "onset_date_raw": to_dd_mon_yyyy(onset_datetime),
                })
    return rows
