# FHIR Mapping Schema — Legacy-to-FHIR MCP Server

Source: `data/legacy.db`
Scope: `Patient`, `Observation`, `Condition` resources only

---

## Patient resource

**Sources:** `patient_identity` (keyed by `mrn`) + `patient_contact` (no shared key)

| Legacy field | Table | FHIR element | Transformation rule |
|---|---|---|---|
| `mrn` | patient_identity | `Patient.identifier` | Direct copy, `system` = internal legacy MRN OID |
| `first_name` + `last_name` | patient_identity | `Patient.name.given` / `.family` | Direct copy |
| `gender_code` | patient_identity | `Patient.gender` | `F` → `female`, `M` → `male`. Not observed in this seed, but code defensively for `U` → `unknown` since the mangling logic supports it |
| `dob_mmddyyyy` | patient_identity | `Patient.birthDate` | Parse `MM/DD/YYYY` → FHIR `date` (`YYYY-MM-DD`) |
| `dob_epoch` | patient_contact | *(cross-check only)* | Parse Unix epoch → date, compare against `dob_mmddyyyy` to confirm join match |
| `full_name` | patient_contact | *(join key only)* | Used to match against `patient_identity.first_name + last_name`, not separately mapped |
| `ssn` | patient_contact | `Patient.identifier` (second entry) | Direct copy, `system` = SSN OID. Mock data only — never real SSNs |
| `phone` | patient_contact | `Patient.telecom` | `system: phone`, direct copy |
| `address_line`, `city`, `state` | patient_contact | `Patient.address` | Combine into FHIR `Address` object |

**Join resolution rule:** Match `patient_identity` to `patient_contact` on normalized `full_name` (case-insensitive, whitespace-trimmed) AND matching date-of-birth (after parsing `dob_mmddyyyy` and `dob_epoch` to a common date format).

**Fallback:** If zero or multiple matches are found, do not guess. Flag the record as `identity_join_unresolved` and exclude contact fields from the returned Patient resource rather than attaching the wrong contact info.

---

## Observation resource

**Source:** `vitals_log`

| Legacy field | FHIR element | Transformation rule |
|---|---|---|
| `mrn` | `Observation.subject` | Direct copy (reference to Patient) |
| `vital_label` | `Observation.code` | Normalize via `LOWER(TRIM(vital_label))`, then map through LOINC lookup table below |
| `value_raw` | `Observation.valueQuantity.value` | Parse to numeric |
| `unit` | `Observation.valueQuantity.unit` | Pass through directly — values are already valid UCUM codes (see unit table below) |
| `recorded_date_yyyymmdd` | `Observation.effectiveDateTime` | Parse `YYYYMMDD` string → FHIR `dateTime` |

### LOINC lookup table

✅ Verified 2026-07-21 against `tx.fhir.org` (live FHIR terminology server, LOINC code system) via `CodeSystem/$lookup`. All 14 original codes matched their official LOINC display name exactly. Two rows were also added below (`systolic blood pressure`, `diastolic blood pressure`) that were missing from this table even though `vitals_log` has carried those readings since the Ticket 1 blood-pressure extraction fix — without them, every BP observation would have hit the `loinc_code_unresolved` fallback.

| Normalized `vital_label` | LOINC code | LOINC display name |
|---|---|---|
| body height | 8302-2 | Body height |
| body weight | 29463-7 | Body weight |
| body temperature | 8310-5 | Body temperature |
| heart rate | 8867-4 | Heart rate |
| respiratory rate | 9279-1 | Respiratory rate |
| oxygen saturation in arterial blood | 2708-6 | Oxygen saturation in Arterial blood |
| body mass index (bmi) [ratio] | 39156-5 | Body mass index (BMI) [Ratio] |
| body mass index (bmi) [percentile] per age and sex | 59576-9 | Body mass index (BMI) [Percentile] Per age and sex |
| pain severity - 0-10 verbal numeric rating [score] - reported | 72514-3 | Pain severity - 0-10 verbal numeric rating [Score] - Reported |
| weight-for-length per age and sex | 77606-2 | Weight-for-length Per age and sex |
| head occipital-frontal circumference | 9843-4 | Head Occipital-frontal circumference |
| head occipital-frontal circumference percentile | 8289-1 | Head Occipital-frontal circumference Percentile |
| left eye intraocular pressure | 79893-4 | Left eye Intraocular pressure |
| right eye intraocular pressure | 79892-6 | Right eye Intraocular pressure |
| systolic blood pressure | 8480-6 | Systolic blood pressure |
| diastolic blood pressure | 8462-4 | Diastolic blood pressure |

**Fallback:** If `vital_label` (after normalization) doesn't match any entry in the lookup table, flag the record as `loinc_code_unresolved` rather than omitting the code or guessing.

### Unit handling

All observed units are already valid UCUM codes — pass through directly:
`cm`, `/min`, `{score}`, `kg/m2`, `%`, `mm[Hg]`, `Cel`, `kg`

**Fallback (missing unit / NULL):** Do not infer a unit from `vital_label` even when it seems obvious. Flag as `unit_missing`, return `valueQuantity.value` populated with `unit` omitted, plus the flag.

**Note on future-dated entries:** Synthea's generated timeline includes dates into 2026+. These pass FHIR structural validation without special handling — not treated as an error case.

---

## Condition resource

**Source:** `conditions_log`

| Legacy field | FHIR element | Transformation rule |
|---|---|---|
| `mrn` | `Condition.subject` | Direct copy (reference to Patient) |
| `note_text` | `Condition.code` | Map through SNOMED-CT keyword lookup table below |
| `onset_date_raw` | `Condition.onsetDateTime` | Parse `DD-Mon-YYYY` (e.g. `15-Mar-2019`) → FHIR `dateTime` |

### SNOMED-CT lookup table

✅ Verified 2026-07-21 against `tx.fhir.org` (live FHIR terminology server serving SNOMED CT International Edition, version 20250201) via `CodeSystem/$lookup` and `ValueSet/$expand`. Direct access to `browser.ihtsdotools.org`'s API returned HTTP 403 (bot-blocked), so this server was used as the terminology-API source instead. 6 of the original 19 codes were wrong and have been corrected below; the other 13 matched their concept's FSN/preferred term exactly.

| `note_text` | SNOMED-CT code | Preferred term |
|---|---|---|
| perennial allergic rhinitis | 232353008 | Perennial allergic rhinitis with seasonal variation |
| acute bacterial sinusitis | 75498004 | Acute bacterial sinusitis |
| medication review due | 314529007 | Medication review due |
| gingivitis | 66383009 | Gingivitis |
| unhealthy alcohol drinking behavior | 10939881000119105 | Unhealthy alcohol drinking behavior |
| suspected disease caused by severe acute respiratory coronavirus 2 | 840544004 | Suspected COVID-19 |
| cough | 49727002 | Cough |
| sputum finding | 248595008 | Sputum finding |
| muscle pain | 68962001 | Muscle pain |
| joint pain | 57676002 | Joint pain |
| fever | 386661006 | Fever |
| loss of taste | 36955009 | Loss of taste |
| disease caused by severe acute respiratory syndrome coronavirus 2 | 840539006 | COVID-19 |
| viral sinusitis | 444814009 | Viral sinusitis |
| acute viral pharyngitis | 195662009 | Acute viral pharyngitis |
| pyelonephritis | 45816000 | Pyelonephritis |
| limited social contact | 423315002 | Limited social contact |
| gingival disease | 18718003 | Gingival disease |
| primary dental caries | 109570002 | Primary dental caries |

**Corrections made during verification:**
- `perennial allergic rhinitis`: 367498001 → 232353008 (367498001 is actually "Seasonal allergic rhinitis" — opposite meaning)
- `acute bacterial sinusitis`: confirmed correct as-is (75498004 is active and exact). A suggested alternative, 444812008, was checked and rejected — it's "Repair of aortic valve using fluoroscopic guidance with contrast," an unrelated procedure code
- `medication review due`: 182836005 → 314529007 (182836005 is "Review of medication," the procedure — not the pending/due situation)
- `unhealthy alcohol drinking behavior`: 225323000 → 10939881000119105 (225323000 is "Smoking cessation education")
- `limited social contact`: 706893006 → 423315002 (706893006 is "Victim of intimate partner abuse")
- `gingival disease`: 109570004 → 18718003 (109570004 does not exist in current SNOMED CT)
- `primary dental caries`: 109585007 → 109570002 (109585007 does not exist in current SNOMED CT)

**Special case — multi-concept free text:** `"educated to high school level, full-time employment, social isolation, stress"` is not a single condition; it's multiple concatenated SDOH (social determinants of health) concepts in one field. This is the deliberate messy-legacy pattern in this dataset.

**Fallback rule:** If `note_text` doesn't match the lookup table exactly (including multi-concept strings like the one above), do not force-fit a SNOMED code. Return the Condition resource with `Condition.code.text` set to the raw note text and a `condition_code_unresolved` flag. Never assign the nearest-sounding code.

---

## Summary of fallback flags used across all resources

| Flag | Resource | Trigger |
|---|---|---|
| `identity_join_unresolved` | Patient | Zero or multiple name+DOB matches across identity/contact tables |
| `loinc_code_unresolved` | Observation | `vital_label` not found in LOINC lookup table |
| `unit_missing` | Observation | `unit` column is NULL |
| `condition_code_unresolved` | Condition | `note_text` not found in SNOMED lookup table, or is multi-concept |

These flags are the enforcement mechanism for the "zero-trust" validation principle in the project architecture: the system never silently guesses when a mapping is ambiguous.
