#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builds a mapping config between two FHIR packages:
- Pairs StructureDefinitions by identical URL (exact matches)
- Optionally suggests mappings by resource 'type' / 'kind' and fuzzy name overlap
- Can emit old-style 'profiles_to_compare' list (IDs + grouped mappings)

Examples:
  python build_config.py \
    --source "…/kbv.ita.erp#1.3.2/package" \
    --target "…/de.gematik.epa.medication#1.0.6-2/package" \
    --suggest-by-type --profiles-to-compare \
    --log-level DEBUG \
    --out config.json
"""

import argparse
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_pkg_meta(package_dir: Path):
    pkg_json = package_dir / "package.json"
    name = None
    version = None
    if pkg_json.exists():
        try:
            data = read_json(pkg_json)
            name = data.get("name")
            version = data.get("version")
        except Exception as e:
            log.debug("package.json konnte nicht gelesen werden: %s", e)

    if not name:
        name = package_dir.parent.name.split("#", 1)[0]
    if not version:
        parent = package_dir.parent.name
        version = parent.split("#", 1)[1] if "#" in parent else "unknown"
    log.debug("Package identifiziert: name=%s, version=%s", name, version)
    return name, version

def normalize_tokens(s: str):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return set(t for t in s.split() if t)

def load_structuredefinitions(package_dir: Path):
    """
    Returns dict[url] = meta, and a list[meta] for iteration.
    meta: {
      'url','version','type','kind','name','title','file','filename'
    }
    """
    metas_by_url = {}
    metas = []
    all_files = list(package_dir.rglob("*.json"))
    log.info("Lese StructureDefinitions aus: %s", package_dir)
    for path in all_files:
        try:
            data = read_json(path)
        except Exception:
            continue
        if data.get("resourceType") != "StructureDefinition":
            continue
        url = data.get("url")
        ver = data.get("version")
        meta = {
            "url": url,
            "version": ver,
            "type": data.get("type"),
            "kind": data.get("kind"),
            "name": data.get("name"),
            "title": data.get("title"),
            "file": path.name,         # Dateiname im package-Verzeichnis
            "filename": str(path),     # voller Pfad
        }
        if url and ver:
            metas_by_url[url] = meta
            metas.append(meta)

    log.info("Gefundene StructureDefinitions: %d (insgesamt Dateien: %d)", len(metas), len(all_files))
    return metas_by_url, metas

def best_target_for_source(src, target_metas):
    """
    Heuristik:
      1) Gleiches kind und type bevorzugen
      2) Falls mehrere Kandidaten: Titel/Name-Token-Overlap
      3) Hardcoded Präferenzen für häufige Paare (Medication, MedicationRequest, MedicationDispense)
    Returns: (target_meta, score) or (None, 0)
    """
    candidates = [t for t in target_metas if t.get("kind") == src.get("kind") and t.get("type") == src.get("type")]
    if not candidates:
        # Für Extensions: manchmal fehlt 'type'; fallback auf kind=complex-type
        if src.get("kind") == "complex-type":
            candidates = [t for t in target_metas if t.get("kind") == "complex-type"]

    if not candidates:
        return None, 0

    # Hardcoded Präferenzen: mappe bestimmte FHIR-Typen auf bekannte ePA-Profile
    pref_by_type_substr = {
        "MedicationRequest": ["epa-medication-request"],
        "MedicationDispense": ["epa-medication-dispense"],
        "Medication": ["epa-medication", "epa-medication-pharmaceutical-product", "epa-medication-pzn-ingredient"],
        "Bundle": ["epa-batch", "emp-"],  # schwach, selten relevant
        "Composition": ["composition"],   # generisch
        "Extension": ["multiple-prescription-extension", "medication-"],  # schwach
    }

    def score_target(t):
        score = 0
        # Name-/Title-Overlap
        st = normalize_tokens(src.get("title") or src.get("name") or "")
        tt = normalize_tokens(t.get("title") or t.get("name") or "")
        overlap = len(st & tt)
        score += overlap

        # Präferenz-Bonus
        ty = src.get("type") or src.get("kind") or ""
        prefs = pref_by_type_substr.get(ty, [])
        tname = (t.get("name") or t.get("title") or t.get("url") or "").lower()
        if any(p in tname for p in prefs):
            score += 3

        # Leichter Bonus, wenn beide URLs ein ähnliches Namespace-Präfix teilen (eher generisch)
        surl = (src.get("url") or "").lower()
        turl = (t.get("url") or "").lower()
        if "epa-medication" in turl and ("medication" in surl or "erp" in surl):
            score += 1

        return score

    scored = [(t, score_target(t)) for t in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0]
    return best

def build_profiles_to_compare(src_metas, tgt_metas, exact_pairs, suggested_pairs):
    """
    Gruppiert mehrere Source-Profile auf ein Target-Profile (ein Eintrag pro Target).
    exact_pairs: list[(src_meta, tgt_meta)]
    suggested_pairs: list[(src_meta, tgt_meta)]
    """
    groups = {}  # key: target.url -> {'target': tgt_meta, 'sources': set(src_meta)}
    def add_pair(s, t, origin="exact"):
        key = t["url"]
        if key not in groups:
            groups[key] = {"target": t, "sources": [], "origin": set()}
        groups[key]["sources"].append(s)
        groups[key]["origin"].add(origin)

    for s, t in exact_pairs:
        add_pair(s, t, origin="exact")
    for s, t in suggested_pairs:
        # vermeide Dubletten
        if (s["url"], t["url"]) in {(es["url"], groups[t["url"]]["target"]["url"]) for es in groups.get(t["url"], {}).get("sources", [])}:
            continue
        add_pair(s, t, origin="suggested")

    items = []
    for key, grp in groups.items():
        t = grp["target"]
        sources = grp["sources"]
        # Ein Eintrag pro Target mit allen zugeordneten Sources
        item = {
            "id": str(uuid.uuid4()),
            "version": "1.0",
            "status": "active",
            "mappings": {
                "sourceprofiles": [
                    {
                        "url": s["url"],
                        "version": s["version"],
                        "file": s["file"]
                    } for s in sources
                ],
                "targetprofile": {
                    "url": t["url"],
                    "version": t["version"],
                    "file": t["file"]
                }
            }
        }
        items.append(item)

    return items

def main():
    ap = argparse.ArgumentParser(description="Erzeuge Mapping-Config für zwei FHIR-Pakete (inkl. typbasierter Vorschläge).")
    ap.add_argument("--source", required=True, type=Path, help="Pfad zum 'package'-Ordner (Quelle)")
    ap.add_argument("--target", required=True, type=Path, help="Pfad zum 'package'-Ordner (Ziel)")
    ap.add_argument("--out", type=Path, help="Ausgabedatei (JSON). Fehlt dies, wird nach STDOUT geschrieben.")
    ap.add_argument("--suggest-by-type", action="store_true", help="Typ-basierte Heuristik aktivieren")
    ap.add_argument("--profiles-to-compare", action="store_true",
                    help="Ausgabe im Format 'profiles_to_compare' (alte Mappings-Config, nur Zuordnung der Profile)")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(levelname)s: %(message)s")

    # Basic Checks
    if not args.source.is_dir():
        log.error("--source ist kein Ordner: %s", args.source)
        return 2
    if not args.target.is_dir():
        log.error("--target ist kein Ordner: %s", args.target)
        return 2

    # Meta + Inhalte laden
    src_name, src_ver = load_pkg_meta(args.source)
    tgt_name, tgt_ver = load_pkg_meta(args.target)

    src_by_url, src_metas = load_structuredefinitions(args.source)
    tgt_by_url, tgt_metas = load_structuredefinitions(args.target)

    # 1) Exakte Paare per identischer URL
    common_urls = sorted(set(src_by_url.keys()) & set(tgt_by_url.keys()))
    log.info("Übereinstimmende URLs: %d", len(common_urls))
    exact_pairs = [(src_by_url[u], tgt_by_url[u]) for u in common_urls]

    # 2) Typ-basierte Vorschläge (Heuristik)
    suggested_pairs = []
    if args.suggest_by_type:
        log.info("Starte Typ-basierte Vorschlagsheuristik…")
        count = 0
        for s in src_metas:
            # Skip, falls schon exaktes Pair existiert
            if s["url"] in common_urls:
                continue
            best = best_target_for_source(s, tgt_metas)
            if not best or best[1] <= 0:
                log.debug("Keine Kandidaten für Typ=%s, Kind=%s (%s)", s.get("type"), s.get("kind"), s.get("url"))
                continue
            t, score = best
            suggested_pairs.append((s, t))
            count += 1
            stitle = s.get("title") or s.get("name")
            ttitle = t.get("title") or t.get("name")
            log.debug("Vorschlag: %s  ->  %s  (type=%s, kind=%s, score=%d)",
                      s["url"], t["url"], s.get("type"), s.get("kind"), score)
        log.info("Typbasierte Vorschläge: %d", count)

    # 3) Ausgabe zusammenstellen
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if args.profiles_to_compare:
        items = build_profiles_to_compare(src_metas, tgt_metas, exact_pairs, suggested_pairs)
        out_obj = {
            # nur die eigentliche Zuordnung; alte Zusatzfelder bleiben weg
            "profiles_to_compare": items
        }
    else:
        # Default-Struktur (comparisons + mappings)
        config = {
            "name": f"{src_name}_{src_ver}_to_{tgt_name}_{tgt_ver}",
            "comparisons": [],
            "mappings": [],
        }
        for s, t in exact_pairs + suggested_pairs:
            config["comparisons"].append({
                "id": str(uuid.uuid4()),
                "comparison": {
                    "sourceprofiles": [{"url": s["url"], "version": s["version"]}],
                    "targetprofile": {"url": t["url"], "version": t["version"]},
                }
            })
            config["mappings"].append({
                "id": str(uuid.uuid4()),
                "version": "1.0",
                "status": "active",
                "mappings": {
                    "sourceprofiles": [{"url": s["url"], "version": s["version"], "file": s["file"]}],
                    "targetprofile": {"url": t["url"], "version": t["version"], "file": t["file"]},
                },
                "last_updated": now_iso
            })
        out_obj = config

    # Schreiben
    text = json.dumps(out_obj, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        log.info("Config geschrieben: %s", args.out)
    else:
        print(text)

if __name__ == "__main__":
    raise SystemExit(main())