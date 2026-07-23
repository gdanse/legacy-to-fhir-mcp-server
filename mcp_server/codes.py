"""LOINC / SNOMED-CT lookup tables.

Transcribed verbatim from the verified tables in
mapping/fhir-mapping-schema.md (Ticket 2) -- that file is the source of
truth for *why* each code was chosen; this module is the executable copy.
Keep the two in sync if either changes.
"""

# Normalized (LOWER(TRIM(vital_label))) -> LOINC code
LOINC_CODES = {
    "body height": "8302-2",
    "body weight": "29463-7",
    "body temperature": "8310-5",
    "heart rate": "8867-4",
    "respiratory rate": "9279-1",
    "oxygen saturation in arterial blood": "2708-6",
    "body mass index (bmi) [ratio]": "39156-5",
    "body mass index (bmi) [percentile] per age and sex": "59576-9",
    "pain severity - 0-10 verbal numeric rating [score] - reported": "72514-3",
    "weight-for-length per age and sex": "77606-2",
    "head occipital-frontal circumference": "9843-4",
    "head occipital-frontal circumference percentile": "8289-1",
    "left eye intraocular pressure": "79893-4",
    "right eye intraocular pressure": "79892-6",
    "systolic blood pressure": "8480-6",
    "diastolic blood pressure": "8462-4",
}

# note_text -> (SNOMED-CT code, preferred term)
SNOMED_CODES = {
    "perennial allergic rhinitis": ("232353008", "Perennial allergic rhinitis with seasonal variation"),
    "acute bacterial sinusitis": ("75498004", "Acute bacterial sinusitis"),
    "medication review due": ("314529007", "Medication review due"),
    "gingivitis": ("66383009", "Gingivitis"),
    "unhealthy alcohol drinking behavior": ("10939881000119105", "Unhealthy alcohol drinking behavior"),
    "suspected disease caused by severe acute respiratory coronavirus 2": ("840544004", "Suspected COVID-19"),
    "cough": ("49727002", "Cough"),
    "sputum finding": ("248595008", "Sputum finding"),
    "muscle pain": ("68962001", "Muscle pain"),
    "joint pain": ("57676002", "Joint pain"),
    "fever": ("386661006", "Fever"),
    "loss of taste": ("36955009", "Loss of taste"),
    "disease caused by severe acute respiratory syndrome coronavirus 2": ("840539006", "COVID-19"),
    "viral sinusitis": ("444814009", "Viral sinusitis"),
    "acute viral pharyngitis": ("195662009", "Acute viral pharyngitis"),
    "pyelonephritis": ("45816000", "Pyelonephritis"),
    "limited social contact": ("423315002", "Limited social contact"),
    "gingival disease": ("18718003", "Gingival disease"),
    "primary dental caries": ("109570002", "Primary dental caries"),
}
