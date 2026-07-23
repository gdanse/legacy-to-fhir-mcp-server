#!/usr/bin/env python3
"""Builds the mock legacy SQLite database from Synthea FHIR output.

Usage: python3 scripts/build_legacy_db.py
Reads:  synthea_output/fhir/*.json
Writes: data/legacy.db
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legacy_data import extract, mangle
from legacy_data.schema import SCHEMA_SQL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FHIR_DIR = os.path.join(ROOT, "synthea_output", "fhir")
DB_PATH = os.path.join(ROOT, "data", "legacy.db")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    n_patients = n_vitals = n_conditions = 0

    for patient_id, entries in extract.load_bundles(FHIR_DIR):
        patient_resource = next(r for r in entries if r["resourceType"] == "Patient")
        patient = extract.extract_patient(patient_resource)
        mrn = mangle.make_mrn(patient["id"])

        identity = mangle.mangle_patient_identity(patient)
        contact = mangle.mangle_patient_contact(patient)
        conn.execute(
            "INSERT INTO patient_identity VALUES (:mrn, :first_name, :last_name, :gender_code, :dob_mmddyyyy)",
            identity,
        )
        conn.execute(
            "INSERT INTO patient_contact VALUES (:full_name, :dob_epoch, :ssn, :phone, :address_line, :city, :state)",
            contact,
        )
        n_patients += 1

        vitals = extract.extract_vitals(entries)
        for row in mangle.mangle_vitals(patient["id"], mrn, vitals):
            conn.execute(
                "INSERT INTO vitals_log VALUES (:mrn, :vital_label, :value_raw, :unit, :recorded_date_yyyymmdd)",
                row,
            )
            n_vitals += 1

        conditions = extract.extract_conditions(entries)
        for row in mangle.mangle_conditions(patient["id"], mrn, conditions):
            conn.execute(
                "INSERT INTO conditions_log VALUES (:mrn, :note_text, :onset_date_raw)",
                row,
            )
            n_conditions += 1

    conn.commit()
    conn.close()
    print(f"Wrote {DB_PATH}")
    print(f"  patients:   {n_patients}")
    print(f"  vitals:     {n_vitals}")
    print(f"  conditions: {n_conditions}")


if __name__ == "__main__":
    main()
