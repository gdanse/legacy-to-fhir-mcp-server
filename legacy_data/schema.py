SCHEMA_SQL = """
DROP TABLE IF EXISTS patient_identity;
DROP TABLE IF EXISTS patient_contact;
DROP TABLE IF EXISTS vitals_log;
DROP TABLE IF EXISTS conditions_log;

-- Table 1 of the fragmented patient record: registration/identity system.
-- dob_mmddyyyy is a plain US-style date string, e.g. "10/30/1954".
CREATE TABLE patient_identity (
    mrn             TEXT PRIMARY KEY,
    first_name      TEXT,
    last_name       TEXT,
    gender_code     TEXT,
    dob_mmddyyyy    TEXT
);

-- Table 2 of the fragmented patient record: a separate contact/billing system.
-- No shared key with patient_identity -- only name + dob, and even those are
-- stored in incompatible shapes (dob_epoch here vs. dob_mmddyyyy above), so
-- joining the two requires normalizing both name and date first.
CREATE TABLE patient_contact (
    full_name       TEXT,
    dob_epoch       INTEGER,
    ssn             TEXT,
    phone           TEXT,
    address_line    TEXT,
    city            TEXT,
    state           TEXT
);

-- recorded_date_yyyymmdd is a bare digit-string date, e.g. "20080228".
-- unit is frequently NULL; when it's NULL the unit sometimes rides along
-- inside value_raw instead (e.g. "70.4 kg").
CREATE TABLE vitals_log (
    mrn                     TEXT,
    vital_label             TEXT,
    value_raw               TEXT,
    unit                    TEXT,
    recorded_date_yyyymmdd  TEXT
);

-- note_text is a denormalized free-text field standing in for a coded
-- Condition -- sometimes a rewritten lay phrase, sometimes two conditions
-- mashed into one comma-separated string.
-- onset_date_raw is yet a third date format, e.g. "23-Dec-1972".
CREATE TABLE conditions_log (
    mrn             TEXT,
    note_text       TEXT,
    onset_date_raw  TEXT
);
"""
