#!/usr/bin/env python3
"""Interactive demo REPL for the README GIF -- type a natural-language query,
see it routed to a tool and returned as validated FHIR, no MCP client needed
(see "Without any MCP client" in the README).

The keyword router below is a simplified stand-in for demo purposes only --
it is NOT the real tool-selection logic. The actual natural-language
understanding that picks between these two tools happens in an MCP client
(e.g. Claude Code), not in this script.

Usage: python3 scripts/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.server import query_legacy_patient_records, translate_vitals_log

_VITALS_KEYWORDS = (
    "weight", "height", "heart rate", "blood pressure", "temperature",
    "vitals", "bmi", "pain", "oxygen", "circumference", "pressure",
)


def _pick_tool(query):
    q = query.lower()
    if any(k in q for k in _VITALS_KEYWORDS):
        return "translate_vitals_log", translate_vitals_log
    return "query_legacy_patient_records", query_legacy_patient_records


def _print_result(tool_name, result):
    bundle = result["bundle"]
    print(f"\n[{tool_name}] {bundle['total']} resource(s) returned, FHIR R4B validated\n")
    for entry in bundle["entry"][:6]:
        r = entry["resource"]
        rt = r["resourceType"]
        if rt == "Patient":
            print(f"   Patient  {r['name'][0]['given'][0]} {r['name'][0]['family']}  DOB {r['birthDate']}")
        elif rt == "Condition":
            coded = "coded" if "coding" in r["code"] else "unresolved"
            print(f"   Condition  {r['code']['text']:35s} ({coded})  onset {r['onsetDateTime']}")
        elif rt == "Observation":
            vq = r["valueQuantity"]
            unit = vq.get("unit", "(unit not on file)")
            print(f"   Observation  {r['code']['text']:20s} {vq['value']:>6}  {unit}  {r['effectiveDateTime']}")
    remaining = bundle["total"] - min(6, len(bundle["entry"]))
    if remaining > 0:
        print(f"   ... ({remaining} more)")
    if result["warnings"]:
        print(f"\n   {len(result['warnings'])} warning(s) flagged -- never guessed, always reported")
    print(f"   validation_failures: {result['validation_failures']}\n")


def main():
    print("Legacy-to-FHIR MCP Server -- type a natural-language query (or 'exit')\n")
    while True:
        try:
            query = input("query> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            continue
        if query.lower() in ("exit", "quit"):
            break
        tool_name, fn = _pick_tool(query)
        result = fn(query)
        _print_result(tool_name, result)


if __name__ == "__main__":
    main()
