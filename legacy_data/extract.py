"""Pulls clean structured records out of Synthea FHIR bundles.

This is the only place that reads FHIR shapes directly. Everything downstream
(mangle.py) works off the plain dicts returned here, not raw FHIR JSON.
"""
import glob
import json
import os


def load_bundles(fhir_dir):
    """Yields (patient_uuid, bundle_entries) for each patient bundle in fhir_dir."""
    for path in sorted(glob.glob(os.path.join(fhir_dir, "*.json"))):
        name = os.path.basename(path)
        if name.startswith("hospitalInformation") or name.startswith("practitionerInformation"):
            continue
        with open(path) as f:
            bundle = json.load(f)
        entries = [e["resource"] for e in bundle.get("entry", [])]
        patient = next((r for r in entries if r["resourceType"] == "Patient"), None)
        if patient is None:
            continue
        yield patient["id"], entries


def extract_patient(patient):
    name = patient.get("name", [{}])[0]
    given = name.get("given", [])
    address = patient.get("address", [{}])[0]
    ssn = next(
        (ident["value"] for ident in patient.get("identifier", [])
         if ident.get("type", {}).get("text") == "Social Security Number"),
        None,
    )
    return {
        "id": patient["id"],
        "first_name": given[0] if given else "",
        "last_name": name.get("family", ""),
        "gender": patient.get("gender", ""),
        "birth_date": patient.get("birthDate", ""),  # FHIR ISO: YYYY-MM-DD
        "phone": next((t["value"] for t in patient.get("telecom", []) if t.get("system") == "phone"), ""),
        "address_line": ", ".join(address.get("line", [])),
        "city": address.get("city", ""),
        "state": address.get("state", ""),
        "ssn": ssn or "",
    }


def extract_vitals(entries):
    vitals = []
    for r in entries:
        if r["resourceType"] != "Observation":
            continue
        categories = [
            c["code"] for cat in r.get("category", []) for c in cat.get("coding", [])
        ]
        if "vital-signs" not in categories:
            continue
        effective_datetime = r.get("effectiveDateTime", "")
        vq = r.get("valueQuantity")
        if vq is not None:
            vitals.append({
                "label": r.get("code", {}).get("text", ""),
                "value": vq.get("value"),
                "unit": vq.get("unit", ""),
                "effective_datetime": effective_datetime,
            })
            continue
        # Panel-style vitals (e.g. blood pressure) carry no top-level
        # valueQuantity -- each sub-measurement lives in "component" instead.
        for component in r.get("component", []):
            cvq = component.get("valueQuantity")
            if cvq is None:
                continue
            vitals.append({
                "label": component.get("code", {}).get("text", ""),
                "value": cvq.get("value"),
                "unit": cvq.get("unit", ""),
                "effective_datetime": effective_datetime,
            })
    return vitals


def extract_conditions(entries):
    conditions = []
    for r in entries:
        if r["resourceType"] != "Condition":
            continue
        text = r.get("code", {}).get("text", "")
        conditions.append({
            "text": text,
            "onset_datetime": r.get("onsetDateTime", ""),
        })
    return conditions
