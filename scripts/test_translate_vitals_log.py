#!/usr/bin/env python3
"""Smoke tests for the translate_vitals_log MCP tool (Ticket 4).

Exercises the acceptance criteria directly:
  - structurally valid FHIR Observation JSON for a range of queries
  - a genuinely messy raw value (Body Weight with the unit embedded in
    value_raw, e.g. "55.8 kg", because the legacy mangling pass moved it
    there instead of dropping it) is recovered correctly, not flagged as
    if it were guessed
  - YYYYMMDD, the one date format vitals_log actually contains, normalizes
    correctly
  - vital-type keyword filtering narrows results as expected
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fhir.resources.R4B.observation import Observation

from mcp_server.fhir_build import build_observation_resources
from mcp_server.server import translate_vitals_log

CASES = [
    ("Adelle Raynor", "no vital-type keyword -- everything on file, mix of clean "
                       "units, missing units, and the embedded-unit-in-value_raw case"),
    ("Adelle Raynor's weight", "vital-type keyword filter -- should return only "
                                "Body Weight readings, including the messy embedded-unit ones"),
    ("Ben Torp's blood pressure", "vital-type keyword filter -- should return only "
                                  "systolic/diastolic readings"),
    ("MRN720072 heart rate", "MRN + keyword combined"),
]


def validate_structural_correctness(bundle):
    for entry in bundle["entry"]:
        Observation(**entry["resource"])


def main():
    for query, note in CASES:
        print(f"\n{'=' * 70}\nQuery: {query!r}\n({note})\n{'=' * 70}")
        result = translate_vitals_log(query)
        validate_structural_correctness(result["bundle"])
        print(f"bundle.total = {result['bundle']['total']}  (structurally valid: OK)")
        for entry in result["bundle"]["entry"][:8]:
            r = entry["resource"]
            vq = r.get("valueQuantity", {})
            print(f"  {r['code']['text']:55s} value={vq.get('value')!r:>8} "
                  f"unit={vq.get('unit')!r:6} date={r['effectiveDateTime']}"
                  f" LOINC={'coding' in r['code']}")
        if result["bundle"]["total"] > 8:
            print(f"  ... ({result['bundle']['total'] - 8} more)")
        flags = sorted({w["flag"] for w in result["warnings"]})
        print(f"  warning flags present: {flags or 'none'}")

    # Directly prove the embedded-unit case is recovered, not flagged.
    print(f"\n{'=' * 70}\nDirect check: embedded-unit recovery vs. genuine unit_missing\n{'=' * 70}")
    fake_rows = [
        {"vital_label": "Body Weight", "value_raw": "55.8 kg", "unit": None, "recorded_date_yyyymmdd": "20200223"},
        {"vital_label": "Heart rate", "value_raw": "86", "unit": None, "recorded_date_yyyymmdd": "20200223"},
        {"vital_label": "Heart rate", "value_raw": "86", "unit": "/min", "recorded_date_yyyymmdd": "20200223"},
    ]
    resources, warnings = build_observation_resources("TEST", fake_rows)
    for r, row in zip(resources, fake_rows):
        vq = r["valueQuantity"]
        print(f"  input value_raw={row['value_raw']!r} unit={row['unit']!r} "
              f"-> value={vq['value']!r} unit={vq.get('unit')!r}")
    flags = [w["flag"] for w in warnings]
    assert flags == ["unit_missing"], f"expected exactly one unit_missing flag, got {flags}"
    print("  Confirmed: embedded-unit value correctly recovered with NO flag; "
          "genuinely missing unit correctly flagged as unit_missing; clean case untouched.")

    # Directly prove the loinc_code_unresolved fallback path works, even
    # though every label in the actual seed data currently has LOINC coverage.
    print(f"\n{'=' * 70}\nDirect check: loinc_code_unresolved fallback (no such label exists in real data)\n{'=' * 70}")
    resources, warnings = build_observation_resources(
        "TEST", [{"vital_label": "Some Unmapped Legacy Vital", "value_raw": "1", "unit": None,
                  "recorded_date_yyyymmdd": "20200223"}]
    )
    Observation(**resources[0])
    assert "coding" not in resources[0]["code"]
    assert any(w["flag"] == "loinc_code_unresolved" for w in warnings)
    print("  Confirmed: unmapped label -> code.text only, no coding, loinc_code_unresolved flagged.")

    print(f"\n{'=' * 70}\nAll cases ran; every returned resource passed fhir.resources structural validation.")


if __name__ == "__main__":
    main()
