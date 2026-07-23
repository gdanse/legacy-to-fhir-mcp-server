"""Schema-conformance gate for every resource either tool is about to return.

This is deliberately independent of fhir_build.py: it doesn't trust that the
mapping logic produced valid FHIR, it re-checks the resource's actual shape
against the FHIR R4B models. If Ticket 2/3/4's mapping logic has a bug that
produces a structurally invalid resource, this is what catches it -- fixing
that bug is out of scope here; this ticket only makes sure it can never
leave the server disguised as valid FHIR.
"""
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.observation import Observation
from fhir.resources.R4B.patient import Patient

_MODELS_BY_RESOURCE_TYPE = {
    "Patient": Patient,
    "Condition": Condition,
    "Observation": Observation,
}


def validate_resource(resource):
    """Returns (True, None) if `resource` passes FHIR R4B structural
    validation, or (False, reason) if it doesn't."""
    resource_type = resource.get("resourceType")
    model = _MODELS_BY_RESOURCE_TYPE.get(resource_type)
    if model is None:
        return False, f"Unknown or unsupported resourceType: {resource_type!r}"
    try:
        model(**resource)
        return True, None
    except Exception as e:
        return False, str(e)
