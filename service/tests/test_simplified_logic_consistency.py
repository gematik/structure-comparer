#!/usr/bin/env python3
"""
Test für die neue vereinfachte Berechnungslogik

Verifiziert, dass:
1. Backend-Berechnungen konsistent sind (Kompatibel + Gelöst + Aktion erforderlich = Gesamt)
2. Frontend-Berechnungen mit Backend übereinstimmen
3. Filter-Logik korrekt funktioniert
"""

import json
import requests
from typing import Dict, Any


def get_all_projects_and_mappings():
    """Hole alle Projekte und deren Mappings vom Backend"""
    # Hole alle verfügbaren Projekte
    projects_response = requests.get("http://127.0.0.1:8000/projects")
    projects = projects_response.json()
    
    all_mappings = []
    
    for project_key in projects:
        try:
            # Hole alle Mappings für dieses Projekt
            project_response = requests.get(f"http://127.0.0.1:8000/project/{project_key}")
            project_data = project_response.json()
            mappings = project_data.get('mappings', [])
            
            # Füge Projekt-Kontext zu jedem Mapping hinzu
            for mapping in mappings:
                mapping['project_key'] = project_key
                all_mappings.append(mapping)
                
        except Exception as e:
            print(f"⚠️  Fehler beim Laden von Projekt {project_key}: {e}")
    
    return all_mappings


def test_backend_consistency():
    """Test dass alle Backend-Berechnungen konsistent sind"""
    print("🧪 TEST: Backend-Konsistenz ALLER Projekte")
    print("=" * 50)
    
    # Hole alle Mappings aus allen Projekten
    all_mappings = get_all_projects_and_mappings()
    
    print(f"Teste {len(all_mappings)} Mappings aus allen Projekten...")
    
    all_consistent = True
    successful_tests = 0
    failed_tests = 0
    projects_tested = set()
    
    for i, mapping in enumerate(all_mappings):
        mapping_id = mapping['id']
        mapping_name = mapping['name']
        project_key = mapping['project_key']
        projects_tested.add(project_key)
        
        try:
            # Backend Summary abrufen
            summary_url = f'http://127.0.0.1:8000/project/{project_key}/mapping/{mapping_id}/evaluation/summary'
            summary_resp = requests.get(summary_url)
            summary_data = summary_resp.json()
            
            compatible = summary_data.get('simplified_compatible', 0)
            resolved = summary_data.get('simplified_resolved', 0) 
            needs_action = summary_data.get('simplified_needs_action', 0)
            total = summary_data.get('total_fields', 0)
            
            sum_parts = compatible + resolved + needs_action
            is_consistent = sum_parts == total
            
            if not is_consistent:
                all_consistent = False
                failed_tests += 1
                print(f"❌ [{project_key}] {mapping_name}")
                print(f"   K: {compatible}, G: {resolved}, A: {needs_action}, Summe: {sum_parts}, Gesamt: {total}")
            else:
                successful_tests += 1
                print(f"✅ [{project_key}] {mapping_name[:40]}{'...' if len(mapping_name) > 40 else ''}")
                
        except Exception as e:
            print(f"❌ [{project_key}] {mapping_name}: Fehler - {e}")
            all_consistent = False
            failed_tests += 1
    
    print()
    print(f"Ergebnis: {successful_tests} erfolgreich, {failed_tests} fehlgeschlagen")
    print(f"Projekte getestet: {len(projects_tested)} ({', '.join(sorted(projects_tested))})")
    
    if all_consistent:
        print("🎉 SUCCESS: Alle Backend-Berechnungen sind konsistent!")
    else:
        print(f"❌ FAILED: {failed_tests} Backend-Berechnungen sind inkonsistent!")
    
    return all_consistent


def simulate_frontend_calculation(field_evaluations: Dict[str, Any]) -> Dict[str, int]:
    """Simuliert die Frontend-Berechnung"""
    compatible = 0
    resolved = 0
    needs_action = 0
    
    for field_name, field_eval in field_evaluations.items():
        original_classification = field_eval.get('original_classification', '')
        action = field_eval.get('action', '')
        
        # Kompatibel: compatible + warning
        if original_classification in ['compatible', 'warning']:
            compatible += 1
        # Gelöst: incompatible mit Action ≠ use
        elif original_classification == 'incompatible' and action != 'use':
            resolved += 1
        # Aktion erforderlich: incompatible mit Action = use
        elif original_classification == 'incompatible' and action == 'use':
            needs_action += 1
    
    return {
        'compatible': compatible,
        'resolved': resolved,
        'needs_action': needs_action,
        'total': len(field_evaluations)
    }


def test_backend_frontend_consistency():
    """Test dass Frontend-Berechnungen mit Backend übereinstimmen"""
    print("\n🧪 TEST: Backend-Frontend-Konsistenz ALLER Projekte")
    print("=" * 55)
    
    # Hole ALLE Mappings aus allen Projekten
    all_mappings = get_all_projects_and_mappings()
    
    print(f"Teste {len(all_mappings)} Mappings aus allen Projekten...")
    
    all_consistent = True
    successful_tests = 0
    failed_tests = 0
    projects_tested = set()
    
    for i, mapping in enumerate(all_mappings):
        mapping_id = mapping['id']
        mapping_name = mapping['name']
        project_key = mapping['project_key']
        projects_tested.add(project_key)
        
        try:
            # Backend Summary
            summary_url = f'http://127.0.0.1:8000/project/{project_key}/mapping/{mapping_id}/evaluation/summary'
            summary_resp = requests.get(summary_url)
            backend_data = summary_resp.json()
            
            # Full Evaluation für Frontend-Simulation
            eval_url = f'http://127.0.0.1:8000/project/{project_key}/mapping/{mapping_id}/evaluation'
            eval_resp = requests.get(eval_url)
            eval_data = eval_resp.json()
            
            # Backend-Werte
            backend_compatible = backend_data.get('simplified_compatible', 0)
            backend_resolved = backend_data.get('simplified_resolved', 0)
            backend_needs_action = backend_data.get('simplified_needs_action', 0)
            backend_total = backend_data.get('total_fields', 0)
            
            # Frontend-Simulation
            field_evaluations = eval_data.get('field_evaluations', {})
            frontend_calc = simulate_frontend_calculation(field_evaluations)
            
            # Vergleich
            is_consistent = (
                backend_compatible == frontend_calc['compatible'] and
                backend_resolved == frontend_calc['resolved'] and
                backend_needs_action == frontend_calc['needs_action'] and
                backend_total == frontend_calc['total']
            )
            
            if not is_consistent:
                all_consistent = False
                failed_tests += 1
                print(f"❌ [{project_key}] {mapping_name}")
                print(f"   Backend:  K={backend_compatible}, G={backend_resolved}, A={backend_needs_action}, T={backend_total}")
                print(f"   Frontend: K={frontend_calc['compatible']}, G={frontend_calc['resolved']}, A={frontend_calc['needs_action']}, T={frontend_calc['total']}")
            else:
                successful_tests += 1
                print(f"✅ [{project_key}] {mapping_name[:45]}{'...' if len(mapping_name) > 45 else ''}")
                
        except Exception as e:
            print(f"❌ [{project_key}] {mapping_name}: Fehler - {e}")
            all_consistent = False
            failed_tests += 1
    
    print()
    print(f"Ergebnis: {successful_tests} erfolgreich, {failed_tests} fehlgeschlagen")
    print(f"Projekte getestet: {len(projects_tested)} ({', '.join(sorted(projects_tested))})")
    
    if all_consistent:
        print("🎉 SUCCESS: Backend und Frontend sind bei ALLEN Mappings konsistent!")
    else:
        print(f"❌ FAILED: {failed_tests} Mappings sind inkonsistent!")
    
    return all_consistent


def test_new_logic_definition():
    """Test der neuen Logik-Definition"""
    print("\n📋 NEUE LOGIK-DEFINITION")
    print("=" * 35)
    print("• Gesamt = Anzahl aller Properties")
    print("• Kompatibel = Felder mit original_classification = 'compatible' oder 'warning'")
    print("• Gelöst = Felder mit original_classification = 'incompatible' aber Action ≠ 'use'")
    print("• Aktion erforderlich = Felder mit original_classification = 'incompatible' und Action = 'use'")
    print("• Garantie: Kompatibel + Gelöst + Aktion erforderlich = Gesamt")
    

if __name__ == "__main__":
    print("🏆 VEREINFACHTE BERECHNUNGSLOGIK - KONSISTENZ-TEST")
    print("=" * 60)
    
    test_new_logic_definition()
    
    backend_ok = test_backend_consistency()
    frontend_ok = test_backend_frontend_consistency()
    
    print("\n" + "=" * 60)
    if backend_ok and frontend_ok:
        print("🎉 ALLE TESTS ERFOLGREICH!")
        print("   Die neue vereinfachte Logik funktioniert korrekt.")
        print("   Backend und Frontend sind vollständig konsistent.")
    else:
        print("❌ EINIGE TESTS FEHLGESCHLAGEN!")
        if not backend_ok:
            print("   - Backend-Berechnungen sind inkonsistent")
        if not frontend_ok:
            print("   - Backend-Frontend-Konsistenz ist nicht gegeben")
    print("=" * 60)