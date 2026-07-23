#!/usr/bin/env python3
"""Smoke tests for the query_legacy_patient_records MCP tool (Ticket 3).

Not a full pytest suite -- exercises the acceptance criteria directly:
  - returns structurally valid FHIR Patient/Condition JSON for a range of queries
  - at least one query hits the split-demographic-table legacy mess pattern
  - fallback flags fire instead of guessing, for ambiguous/unmapped cases
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.patient import Patient

from mcp_server.server import query_legacy_patient_records

CASES = [
    ("MRN978623", "exact MRN match (name has a non-ASCII character: Niño)"),
    ("Ben Torp", "fuzzy name match without Synthea's trailing digits -- "
                 "exercises the split patient_identity/patient_contact join"),
    ("Sawayn", "ambiguous: two different patients share this last name"),
    ("Zzyzx Nonexistent", "no match"),
    ("Cathrine Ankunding", "patient with several free-text conditions that "
                           "won't resolve to a SNOMED code"),
]


def validate_structural_correctness(bundle):
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] == "Patient":
            Patient(**resource)
        elif resource["resourceType"] == "Condition":
            Condition(**resource)
        else:
            raise AssertionError(f"Unexpected resourceType: {resource['resourceType']}")


def main():
    for query, note in CASES:
        print(f"\n{'=' * 70}\nQuery: {query!r}\n({note})\n{'=' * 70}")
        result = query_legacy_patient_records(query)
        validate_structural_correctness(result["bundle"])
        print(f"bundle.total = {result['bundle']['total']}  (structurally valid: OK)")
        for entry in result["bundle"]["entry"]:
            r = entry["resource"]
            if r["resourceType"] == "Patient":
                print(f"  Patient/{r['id']}: {r['name'][0]['given'][0]} {r['name'][0]['family']}"
                      f", DOB {r['birthDate']}, has address: {'address' in r}")
            else:
                coded = "coding" in r["code"]
                print(f"  Condition: \"{r['code']['text']}\" onset {r['onsetDateTime']}"
                      f" (SNOMED resolved: {coded})")
        if result["warnings"]:
            print("  warnings:")
            for w in result["warnings"]:
                print(f"    [{w['flag']}] {w['detail']}")
        else:
            print("  warnings: none")

    print(f"\n{'=' * 70}\nAll cases ran; every returned resource passed fhir.resources structural validation.")


if __name__ == "__main__":
    main()
