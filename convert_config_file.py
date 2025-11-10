#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import argparse
from typing import Dict, Any
import yaml

# 1) Optionale Feldumbenennungen (Alt -> Neu). Bei Bedarf erweitern.
EXACT_NAME_REWRITES: Dict[str, str] = {
    "MedicationRequest.extension:BVG": "MedicationRequest.extension:isBvg.url",
    # Beispiel: weitere Umbenennungen hier eintragen
    # "MedicationRequest.extension:Mehrfachverordnung": "MedicationRequest.extension:multiplePrescription"
}

def apply_name_rewrite(name: str) -> str:
    return EXACT_NAME_REWRITES.get(name, name)

def map_classification_to_action(classification: str) -> str:
    """
    Klassifikation wird im Regelfall 1:1 zur action übernommen.
    Bekannte Werte: not_use, copy_from, copy_to, empty, fixed, manual, medication_service, use
    """
    return classification

def convert(old: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erwartet Struktur:
    {
      "<uuid>": {
        "<fieldName>": {
          "classification": "...",
          "extra": "...",      # optional
          "remark": "..."      # optional
        },
        ...
      },
      ...
    }

    Liefert:
    {
      "entries": [
        {
          "id": "<uuid>",
          "fields": [
            {
              "name": "<fieldName (ggf. umbenannt)>",
              "action": "<mapped from classification>",
              "fixed": "<value or null>",
              "other": "<value or null>",
              "remark": "<value or null>"
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    entries = []

    for uuid, fields_map in old.items():
        fields_out = []
        # Iterationsreihenfolge stabilisieren (optional)
        for name in sorted(fields_map.keys()):
            v = fields_map[name] or {}
            classification = v.get("classification")
            extra = v.get("extra")
            remark = v.get("remark")

            action = map_classification_to_action(classification or "")
            fixed_val = None
            other_val = None

            # Regeln:
            # - fixed  -> fixed = extra
            # - copy_* -> other = extra
            # - sonst  -> fixed/other = None
            if action == "fixed":
                fixed_val = extra
            elif action in ("copy_from", "copy_to"):
                other_val = extra
            else:
                # für andere Aktionen ignorieren wir 'extra' standardmäßig
                pass

            fields_out.append({
                "action": action,
                "fixed": fixed_val,
                "name": apply_name_rewrite(name),
                "other": other_val,
                "remark": remark if remark is not None else None
            })

        entries.append({
            "id": uuid,
            "fields": fields_out
        })

    return {"entries": entries}

def main():
    parser = argparse.ArgumentParser(
        description="Konvertiert Mapping-YAML vom Alt- ins Neu-Format."
    )
    parser.add_argument("infile", nargs="?", default="-", help="Eingabedatei (YAML), '-' für STDIN")
    parser.add_argument("outfile", nargs="?", default="-", help="Ausgabedatei (YAML), '-' für STDOUT")
    args = parser.parse_args()

    # YAML einlesen
    if args.infile == "-" or args.infile is None:
        old_data = yaml.safe_load(sys.stdin.read())
    else:
        with open(args.infile, "r", encoding="utf-8") as f:
            old_data = yaml.safe_load(f)

    if not isinstance(old_data, dict):
        raise SystemExit("Eingabe muss ein Mapping (dict) auf Top-Level sein.")

    new_data = convert(old_data)

    # YAML ausgeben
    dump_kwargs = dict(allow_unicode=True, sort_keys=False)
    if args.outfile == "-" or args.outfile is None:
        yaml.safe_dump(new_data, sys.stdout, **dump_kwargs)
    else:
        with open(args.outfile, "w", encoding="utf-8") as f:
            yaml.safe_dump(new_data, f, **dump_kwargs)

if __name__ == "__main__":
    main()