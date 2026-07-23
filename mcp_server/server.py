import os
import sys

# Runs as a standalone script launched by absolute path (see .mcp.json), so
# only mcp_server/ itself would land on sys.path by default -- add the
# project root too, or the `from mcp_server import ...` below fails.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

from mcp_server import fhir_build, legacy_repo, validation

mcp = FastMCP("legacy-to-fhir-server")


def _append_if_valid(resource, mrn, entries, validation_failures):
    """The zero-trust gate (Ticket 5): every resource passes through FHIR
    schema validation here before it can reach a returned Bundle. There is
    no path to `entries` that skips this call -- a resource that fails is
    excluded from the bundle and reported in validation_failures instead,
    never returned as if it were valid."""
    is_valid, reason = validation.validate_resource(resource)
    if is_valid:
        entries.append({"resource": resource})
    else:
        validation_failures.append({
            "resourceType": resource.get("resourceType"),
            "mrn": mrn,
            "resource": resource,
            "reason": reason,
        })


@mcp.tool()
def query_legacy_patient_records(query: str) -> dict:
    """Look up a patient's identity/demographic and condition (diagnosis / problem list)
    data from the mock legacy healthcare database, translated into FHIR Patient and
    Condition resources.

    Use this for questions about WHO a patient is (name, date of birth, gender, address,
    phone, identifiers) or WHAT conditions/diagnoses are on their problem list. Accepts a
    natural-language reference to a single patient: a name ("Ben Torp"), a legacy MRN
    ("MRN720072"), or both.

    Do NOT use this for vital signs, lab values, or other numeric observations (heart rate,
    weight, blood pressure, etc.) -- use translate_vitals_log for those instead. This tool
    never returns Observation resources.

    Read-only: this tool cannot create, modify, or delete any record.

    Every resource in the returned bundle has passed FHIR R4B schema validation --
    this tool has no path that returns a resource without that check. Anything that
    failed validation is excluded from the bundle and reported in
    `validation_failures` instead, never returned as if it were valid.

    Returns: {"bundle": <FHIR searchset Bundle of Patient + Condition resources>,
              "warnings": [<flags for anything that couldn't be unambiguously resolved>],
              "validation_failures": [<resources that failed FHIR schema validation
                                       and were excluded from the bundle, with why>]}.
    A warning never means a guess was made silently -- it means the tool deliberately
    left a value unresolved (e.g. `identity_join_unresolved` if the two fragmented legacy
    demographic tables couldn't be matched with confidence, `condition_code_unresolved` if
    a free-text condition note isn't in the SNOMED-CT lookup table, or
    `ambiguous_patient_match` / `no_match` if the query itself didn't resolve to exactly
    one patient).
    """
    conn = legacy_repo.get_connection()
    try:
        matches = legacy_repo.resolve_patient(conn, query)

        if not matches:
            return {
                "bundle": {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []},
                "warnings": [{"flag": "no_match", "detail": f"No patient matched query: {query!r}"}],
                "validation_failures": [],
            }

        all_warnings = []
        if len(matches) > 1:
            all_warnings.append({
                "flag": "ambiguous_patient_match",
                "detail": f"{len(matches)} patients matched query {query!r} with similar "
                          f"confidence; returning all rather than guessing one.",
                "matched_mrns": [row["mrn"] for row in matches],
            })

        entries = []
        validation_failures = []
        for identity_row in matches:
            mrn = identity_row["mrn"]
            contact_row, ambiguous = legacy_repo.find_contact_for_identity(conn, identity_row)
            patient, patient_warnings = fhir_build.build_patient_resource(identity_row, contact_row, ambiguous)
            _append_if_valid(patient, mrn, entries, validation_failures)
            all_warnings.extend(patient_warnings)

            condition_rows = legacy_repo.get_conditions(conn, mrn)
            conditions, condition_warnings = fhir_build.build_condition_resources(mrn, condition_rows)
            for condition in conditions:
                _append_if_valid(condition, mrn, entries, validation_failures)
            all_warnings.extend(condition_warnings)

        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(entries),
            "entry": entries,
        }
        return {"bundle": bundle, "warnings": all_warnings, "validation_failures": validation_failures}
    finally:
        conn.close()


@mcp.tool()
def translate_vitals_log(query: str) -> dict:
    """Look up a patient's vital signs / lab observation data from the mock legacy
    healthcare database, translated into FHIR Observation resources.

    Use this for questions about vital signs, lab values, or other numeric
    measurements -- heart rate, blood pressure, weight, height, temperature,
    respiratory rate, oxygen saturation, BMI, pain score, intraocular pressure, head
    circumference, etc. Accepts a natural-language reference to a single patient (a
    name, e.g. "Ben Torp", or a legacy MRN, e.g. "MRN720072"), optionally combined
    with a vital-type keyword (e.g. "Ben Torp's blood pressure", "weight for
    MRN720072") to narrow the results -- omit the keyword to get everything on file.

    Do NOT use this for patient identity/demographic data or diagnoses/conditions --
    use query_legacy_patient_records for those instead. This tool never returns
    Patient or Condition resources.

    Read-only: this tool cannot create, modify, or delete any record.

    Every resource in the returned bundle has passed FHIR R4B schema validation --
    this tool has no path that returns a resource without that check. Anything that
    failed validation is excluded from the bundle and reported in
    `validation_failures` instead, never returned as if it were valid.

    Returns: {"bundle": <FHIR searchset Bundle of Observation resources>,
              "warnings": [<flags for anything that couldn't be unambiguously resolved>],
              "validation_failures": [<resources that failed FHIR schema validation
                                       and were excluded from the bundle, with why>]}.
    A warning never means a guess was made silently -- it means the tool deliberately
    left a value unresolved: `loinc_code_unresolved` if a vital's label isn't in the
    LOINC lookup table, `unit_missing` if the legacy unit column was NULL (a unit is
    never inferred from the vital's name), `vital_value_unparseable` if the raw legacy
    value couldn't be parsed as a number at all, or `ambiguous_patient_match` /
    `no_match` if the query itself didn't resolve to exactly one patient.
    """
    conn = legacy_repo.get_connection()
    try:
        matches = legacy_repo.resolve_patient(conn, query)

        if not matches:
            return {
                "bundle": {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []},
                "warnings": [{"flag": "no_match", "detail": f"No patient matched query: {query!r}"}],
                "validation_failures": [],
            }

        all_warnings = []
        if len(matches) > 1:
            all_warnings.append({
                "flag": "ambiguous_patient_match",
                "detail": f"{len(matches)} patients matched query {query!r} with similar "
                          f"confidence; returning all rather than guessing one.",
                "matched_mrns": [row["mrn"] for row in matches],
            })

        vital_type_filter = legacy_repo.extract_vital_type_filter(query)

        entries = []
        validation_failures = []
        for identity_row in matches:
            mrn = identity_row["mrn"]
            vital_rows = legacy_repo.get_vitals(conn, mrn)
            observations, observation_warnings = fhir_build.build_observation_resources(
                mrn, vital_rows, vital_type_filter
            )
            for observation in observations:
                _append_if_valid(observation, mrn, entries, validation_failures)
            all_warnings.extend(observation_warnings)

        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(entries),
            "entry": entries,
        }
        return {"bundle": bundle, "warnings": all_warnings, "validation_failures": validation_failures}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()
