#!/usr/bin/env python3
"""Prints direct-query evidence of each legacy mess pattern in data/legacy.db."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "legacy.db")


def show(title, sql):
    print(f"\n=== {title} ===")
    for row in conn.execute(sql):
        print(dict(row))


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

show("1. Four date formats across four tables/fields", """
    SELECT * FROM (SELECT 'patient_identity.dob_mmddyyyy' AS field, dob_mmddyyyy AS sample FROM patient_identity LIMIT 2)
    UNION ALL
    SELECT * FROM (SELECT 'patient_contact.dob_epoch', CAST(dob_epoch AS TEXT) FROM patient_contact LIMIT 2)
    UNION ALL
    SELECT * FROM (SELECT 'vitals_log.recorded_date_yyyymmdd', recorded_date_yyyymmdd FROM vitals_log LIMIT 2)
    UNION ALL
    SELECT * FROM (SELECT 'conditions_log.onset_date_raw', onset_date_raw FROM conditions_log LIMIT 2)
""")

show("2. Denormalized free-text conditions (multiple conditions in one field)", """
    SELECT mrn, note_text, onset_date_raw FROM conditions_log
    WHERE note_text LIKE '%,%' LIMIT 5
""")

show("3. Missing or embedded vital units", """
    SELECT vital_label, value_raw, unit FROM vitals_log
    WHERE unit IS NULL LIMIT 5
""")

show("4. Fragmented patient record: fuzzy join across two tables, no shared key", """
    SELECT a.mrn, a.first_name, a.last_name, a.dob_mmddyyyy,
           b.full_name, b.phone, b.city
    FROM patient_identity a
    JOIN patient_contact b
      ON b.full_name = a.last_name || ', ' || a.first_name
      AND strftime('%Y%m%d', datetime(b.dob_epoch, 'unixepoch'))
          = substr(a.dob_mmddyyyy, 7, 4) || substr(a.dob_mmddyyyy, 1, 2) || substr(a.dob_mmddyyyy, 4, 2)
    LIMIT 5
""")
