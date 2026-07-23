"""Builds FHIR Patient and Condition resources from legacy rows, per the
Ticket 2 mapping schema (mapping/fhir-mapping-schema.md).

Every fallback path returns a plain, structurally valid FHIR resource --
never a guessed code -- plus a sibling warning describing which Ticket 2
flag fired and why.
"""
import re

from mcp_server.codes import LOINC_CODES, SNOMED_CODES
from mcp_server.datetimes import parse_dd_mon_yyyy, parse_mmddyyyy, parse_yyyymmdd

_GENDER_MAP = {"M": "male", "F": "female", "U": "unknown"}

_VITALS_CATEGORY = {
    "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
        "code": "vital-signs",
        "display": "Vital signs",
    }],
}

# "55.8 kg" -> ("55.8", "kg"). Only ever seen on Body Weight rows in this
# dataset (see legacy_data/mangle.py), but written generically.
_EMBEDDED_UNIT_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s+(\S+)\s*$")


def build_patient_resource(identity_row, contact_row, join_ambiguous):
    warnings = []
    mrn = identity_row["mrn"]

    identifiers = [{"system": "urn:legacy:mrn", "value": mrn}]
    patient = {
        "resourceType": "Patient",
        "id": mrn,
        "identifier": identifiers,
        "name": [{
            "family": identity_row["last_name"],
            "given": [identity_row["first_name"]],
        }],
        "gender": _GENDER_MAP.get(identity_row["gender_code"], "unknown"),
        "birthDate": parse_mmddyyyy(identity_row["dob_mmddyyyy"]),
    }

    if contact_row is not None:
        identifiers.append({"system": "http://hl7.org/fhir/sid/us-ssn", "value": contact_row["ssn"]})
        patient["telecom"] = [{"system": "phone", "value": contact_row["phone"]}]
        patient["address"] = [{
            "line": [contact_row["address_line"]],
            "city": contact_row["city"],
            "state": contact_row["state"],
        }]

    if join_ambiguous:
        warnings.append({
            "flag": "identity_join_unresolved",
            "resource": "Patient",
            "mrn": mrn,
            "detail": "Zero or multiple patient_contact matches by name+DOB; "
                      "contact fields (address/phone/SSN) omitted rather than guessed.",
        })

    return patient, warnings


def build_condition_resources(mrn, condition_rows):
    resources = []
    warnings = []

    for row in condition_rows:
        note_text = row["note_text"]
        normalized = note_text.strip().lower()
        code = {"text": note_text}

        lookup = SNOMED_CODES.get(normalized)
        if lookup:
            snomed_code, preferred_term = lookup
            code["coding"] = [{
                "system": "http://snomed.info/sct",
                "code": snomed_code,
                "display": preferred_term,
            }]
        else:
            warnings.append({
                "flag": "condition_code_unresolved",
                "resource": "Condition",
                "mrn": mrn,
                "note_text": note_text,
                "detail": "note_text not found in the SNOMED-CT lookup table (often because "
                          "it's multi-concept free text); code.text set to the raw legacy "
                          "value with no coding assigned, per Ticket 2's fallback rule.",
            })

        resources.append({
            "resourceType": "Condition",
            "subject": {"reference": f"Patient/{mrn}"},
            "code": code,
            "onsetDateTime": parse_dd_mon_yyyy(row["onset_date_raw"]),
        })

    return resources, warnings


def _resolve_value_and_unit(value_raw, unit_column):
    """Three cases seen in vitals_log:

    1. value_raw is a plain number and unit_column is populated -- clean.
    2. value_raw is a plain number but unit_column is NULL -- genuinely
       missing; per Ticket 2, do not infer a unit, flag unit_missing.
    3. value_raw has a unit embedded in the string (e.g. "55.8 kg") because
       the mangling pass moved it there instead of dropping it -- this is
       recovering data that's actually present, not guessing, so no flag.

    Returns (value: float, unit: str | None, flag: str | None).
    """
    try:
        return float(value_raw), unit_column, (None if unit_column else "unit_missing")
    except ValueError:
        pass

    m = _EMBEDDED_UNIT_PATTERN.match(value_raw)
    if m:
        return float(m.group(1)), m.group(2), None

    return None, None, "vital_value_unparseable"


def build_observation_resources(mrn, vital_rows, vital_type_filter=None):
    resources = []
    warnings = []

    for row in vital_rows:
        normalized_label = row["vital_label"].strip().lower()
        if vital_type_filter is not None and normalized_label not in vital_type_filter:
            continue

        value, unit, value_flag = _resolve_value_and_unit(row["value_raw"], row["unit"])

        code = {"text": row["vital_label"]}
        loinc_code = LOINC_CODES.get(normalized_label)
        if loinc_code:
            code["coding"] = [{"system": "http://loinc.org", "code": loinc_code, "display": row["vital_label"]}]
        else:
            warnings.append({
                "flag": "loinc_code_unresolved",
                "resource": "Observation",
                "mrn": mrn,
                "vital_label": row["vital_label"],
                "detail": "Normalized vital_label not found in the LOINC lookup table; "
                          "code.text set to the raw legacy label with no coding assigned.",
            })

        observation = {
            "resourceType": "Observation",
            "status": "final",
            "category": [_VITALS_CATEGORY],
            "subject": {"reference": f"Patient/{mrn}"},
            "code": code,
            "effectiveDateTime": parse_yyyymmdd(row["recorded_date_yyyymmdd"]),
        }

        if value_flag == "vital_value_unparseable":
            warnings.append({
                "flag": "vital_value_unparseable",
                "resource": "Observation",
                "mrn": mrn,
                "vital_label": row["vital_label"],
                "value_raw": row["value_raw"],
                "detail": "value_raw did not parse as a plain number or a number+unit pair; "
                          "omitting valueQuantity entirely rather than guessing a value.",
            })
        else:
            value_quantity = {"value": value}
            if unit:
                value_quantity["unit"] = unit
                value_quantity["system"] = "http://unitsofmeasure.org"
                value_quantity["code"] = unit
            observation["valueQuantity"] = value_quantity
            if value_flag == "unit_missing":
                warnings.append({
                    "flag": "unit_missing",
                    "resource": "Observation",
                    "mrn": mrn,
                    "vital_label": row["vital_label"],
                    "detail": "unit column is NULL; valueQuantity.value is populated with "
                              "unit omitted rather than inferred from vital_label, per Ticket 2's fallback rule.",
                })

        resources.append(observation)

    return resources, warnings
