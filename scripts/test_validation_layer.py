#!/usr/bin/env python3
"""Smoke tests for the Ticket 5 schema validation gate.

Exercises the acceptance criteria directly, against the real tool functions
(not just validate_resource() in isolation) so the test actually proves
there's no bypass path:
  - a deliberately malformed row makes it all the way through resolution and
    mapping, then gets excluded from the bundle and reported in
    validation_failures instead of being returned as if it were valid
  - previously-passing queries from Tickets 3/4 still return zero
    validation_failures (no false positives from the new gate)
"""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server import legacy_repo
from mcp_server.server import query_legacy_patient_records, translate_vitals_log

REAL_DB_PATH = legacy_repo.DB_PATH


def make_corrupted_db_copy():
    """Copies the real DB to a scratch temp file, then injects two rows that
    are deliberately impossible to turn into valid FHIR: a patient with an
    out-of-range birth date (month 13, day 45) and a vitals reading with a
    garbage recorded-date string. Nothing in Tickets 1/3/4 is touched --
    this is a standalone copy for this test only."""
    tmp_path = os.path.join(tempfile.mkdtemp(), "legacy_corrupted.db")
    shutil.copyfile(REAL_DB_PATH, tmp_path)

    conn = sqlite3.connect(tmp_path)
    conn.execute(
        "INSERT INTO patient_identity VALUES ('MRN000001', 'Test', 'BadDate', 'M', '13/45/2020')"
    )
    conn.execute(
        "INSERT INTO vitals_log VALUES ('MRN720072', 'Heart rate', '999', NULL, '0000ZZ99')"
    )
    conn.commit()
    conn.close()
    return tmp_path


def find_failure(validation_failures, resource_type, mrn):
    return next(
        (f for f in validation_failures if f["resourceType"] == resource_type and f["mrn"] == mrn),
        None,
    )


def main():
    tmp_db = make_corrupted_db_copy()
    legacy_repo.DB_PATH = tmp_db
    try:
        print("=" * 70)
        print("Malformed input #1: Patient with an impossible birthDate (13/45/2020)")
        print("=" * 70)
        result = query_legacy_patient_records("MRN000001")
        bad_patient_ids = [e["resource"]["id"] for e in result["bundle"]["entry"]
                            if e["resource"]["resourceType"] == "Patient" and e["resource"]["id"] == "MRN000001"]
        assert not bad_patient_ids, "malformed Patient leaked into the bundle -- validation gate did not catch it"
        failure = find_failure(result["validation_failures"], "Patient", "MRN000001")
        assert failure is not None, "malformed Patient was dropped but not reported in validation_failures"
        print(f"  Excluded from bundle: confirmed (bundle.total={result['bundle']['total']})")
        print(f"  Reported in validation_failures: reason={failure['reason'][:200]}...")

        print(f"\n{'=' * 70}")
        print("Malformed input #2: Observation with an unparseable recorded_date_yyyymmdd ('0000ZZ99')")
        print("=" * 70)
        result = translate_vitals_log("MRN720072 heart rate")
        garbage_entries = [e for e in result["bundle"]["entry"] if e["resource"].get("effectiveDateTime", "").startswith("0000")]
        assert not garbage_entries, "malformed Observation leaked into the bundle -- validation gate did not catch it"
        failure = find_failure(result["validation_failures"], "Observation", "MRN720072")
        assert failure is not None, "malformed Observation was dropped but not reported in validation_failures"
        print(f"  Excluded from bundle: confirmed (real heart-rate readings for MRN720072 still present: "
              f"{result['bundle']['total']} entries)")
        print(f"  Reported in validation_failures: reason={failure['reason'][:200]}...")
    finally:
        legacy_repo.DB_PATH = REAL_DB_PATH

    print(f"\n{'=' * 70}")
    print("No false positives: re-running previously-passing Ticket 3/4 queries against the real DB")
    print("=" * 70)
    checks = [
        (query_legacy_patient_records, "MRN978623"),
        (query_legacy_patient_records, "Ben Torp"),
        (query_legacy_patient_records, "Sawayn"),
        (translate_vitals_log, "Adelle Raynor's weight"),
        (translate_vitals_log, "Ben Torp's blood pressure"),
    ]
    for tool, query in checks:
        result = tool(query)
        assert result["validation_failures"] == [], (
            f"false positive: {tool.__name__}({query!r}) reported validation_failures "
            f"on data that previously passed: {result['validation_failures']}"
        )
        print(f"  {tool.__name__}({query!r}): bundle.total={result['bundle']['total']}, "
              f"validation_failures=[] -- OK")

    print(f"\n{'=' * 70}\nAll validation-layer checks passed.")


if __name__ == "__main__":
    main()
