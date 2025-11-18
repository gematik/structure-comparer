#!/usr/bin/env python3
"""
Test der Filter-Konsistenz mit der neuen vereinfachten Logik
"""

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


def test_filter_consistency():
    """Test dass die Filter-Zählungen mit den Status-Karten übereinstimmen"""
    print("🔍 TEST: Filter-Konsistenz ALLER Projekte")
    print("=" * 50)
    
    # Hole ALLE Mappings aus allen Projekten
    all_mappings = get_all_projects_and_mappings()
    
    print(f"Teste Filter-Konsistenz für {len(all_mappings)} Mappings aus allen Projekten...")
    
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
            # Backend Summary (Status-Karten-Werte)
            summary_url = (f'http://127.0.0.1:8000/project/{project_key}/mapping/'
                           f'{mapping_id}/evaluation/summary')
            summary_resp = requests.get(summary_url)
            summary_data = summary_resp.json()
            
            backend_compatible = summary_data.get('simplified_compatible', 0)
            backend_resolved = summary_data.get('simplified_resolved', 0)
            backend_needs_action = summary_data.get('simplified_needs_action', 0)
            
            # Hole detaillierte Evaluation für Filter-Simulation
            eval_url = (f'http://127.0.0.1:8000/project/{project_key}/mapping/'
                        f'{mapping_id}/evaluation')
            eval_resp = requests.get(eval_url)
            eval_data = eval_resp.json()
            field_evaluations = eval_data.get('field_evaluations', {})
            
            # Simuliere Filter-Logik
            filter_compatible = 0
            filter_resolved = 0
            filter_needs_action = 0
            
            for field_name, field_eval in field_evaluations.items():
                original_classification = field_eval.get('original_classification', '')
                action = field_eval.get('action', '')
                
                # Filter-Logik entspricht der neuen Backend-Logik
                if original_classification in ['compatible', 'warning']:
                    filter_compatible += 1
                elif original_classification == 'incompatible' and action != 'use':
                    filter_resolved += 1
                elif original_classification == 'incompatible' and action == 'use':
                    filter_needs_action += 1
            
            # Vergleich
            compatible_match = backend_compatible == filter_compatible
            resolved_match = backend_resolved == filter_resolved
            needs_action_match = backend_needs_action == filter_needs_action
            
            all_match = compatible_match and resolved_match and needs_action_match
            
            if not all_match:
                all_consistent = False
                failed_tests += 1
                print(f"❌ {i+1}. {mapping_name}")
                print(f"   Status-Karten: K={backend_compatible}, G={backend_resolved}, A={backend_needs_action}")
                print(f"   Filter-Zählung: K={filter_compatible}, G={filter_resolved}, A={filter_needs_action}")
                print("     → Kompatibel-Filter stimmt nicht überein!")
                if filter_resolved != backend_resolved:
                    print("     → Gelöst-Filter stimmt nicht überein!")
                if filter_needs_action != backend_needs_action:
                    print("     → Aktion erforderlich-Filter stimmt nicht überein!")
            else:
                successful_tests += 1
                print(f"✅ {i+1}. {mapping_name[:60]}{'...' if len(mapping_name) > 60 else ''}")
                
        except Exception as e:
            print(f"❌ {i+1}. {mapping_name}: Fehler - {e}")
            all_consistent = False
            failed_tests += 1
    
    print()
    print(f"Ergebnis: {successful_tests} erfolgreich, {failed_tests} fehlgeschlagen")
    
    if all_consistent:
        print("🎉 SUCCESS: Filter-Zählungen stimmen bei ALLEN Mappings mit Status-Karten überein!")
    else:
        print(f"❌ FAILED: {failed_tests} von {len(all_mappings)} Mappings haben inkonsistente Filter!")
    
    return all_consistent


def test_detailed_breakdown_all_mappings():
    """Zeigt eine detaillierte Aufschlüsselung für alle Mappings"""
    print("\n📊 DETAILLIERTE AUFSCHLÜSSELUNG - ALLE PROJEKTE")
    print("=" * 60)
    
    # Hole alle Mappings aus allen Projekten
    all_mappings = get_all_projects_and_mappings()
    
    print(f"Analysiere {len(all_mappings)} Mappings aus allen Projekten...")
    
    total_compatible = 0
    total_warning = 0
    total_resolved = 0
    total_needs_action = 0
    total_fields = 0
    
    projects_tested = set()
    
    for i, mapping in enumerate(all_mappings):
        mapping_id = mapping['id']
        mapping_name = mapping['name']
        project_key = mapping['project_key']
        projects_tested.add(project_key)
        
        try:
            # Hole detaillierte Evaluation
            eval_url = (f'http://127.0.0.1:8000/project/{project_key}/mapping/'
                        f'{mapping_id}/evaluation')
            eval_resp = requests.get(eval_url)
            eval_data = eval_resp.json()
            field_evaluations = eval_data.get('field_evaluations', {})
            
            # Analysiere die Kategorien
            compatible_count = 0
            warning_count = 0
            resolved_count = 0
            needs_action_count = 0
            
            resolved_actions = {}
            
            for field_name, field_eval in field_evaluations.items():
                original = field_eval.get('original_classification', '')
                action = field_eval.get('action', '')
                
                if original == 'compatible':
                    compatible_count += 1
                elif original == 'warning':
                    warning_count += 1
                elif original == 'incompatible' and action != 'use':
                    resolved_count += 1
                    resolved_actions[action] = resolved_actions.get(action, 0) + 1
                elif original == 'incompatible' and action == 'use':
                    needs_action_count += 1
            
            mapping_total = len(field_evaluations)
            
            print(f"\n{i+1}. {mapping_name} [Projekt: {project_key}]")
            print(f"   Compatible: {compatible_count}, Warning: {warning_count} → "
                  f"Kompatibel: {compatible_count + warning_count}")
            print(f"   Gelöst: {resolved_count} (Actions: {dict(resolved_actions)})")
            print(f"   Aktion erforderlich: {needs_action_count}")
            print(f"   Gesamt: {mapping_total}")
            
            # Akkumuliere Gesamtstatistiken
            total_compatible += compatible_count
            total_warning += warning_count
            total_resolved += resolved_count
            total_needs_action += needs_action_count
            total_fields += mapping_total
            
        except Exception as e:
            print(f"\n{i+1}. {mapping_name} [Projekt: {project_key}]: Fehler - {e}")
    
    print("\n" + "=" * 55)
    print(f"GESAMTSTATISTIK ALLER {len(all_mappings)} MAPPINGS aus "
          f"{len(projects_tested)} Projekten:")
    print(f"Compatible Felder: {total_compatible}")
    print(f"Warning Felder: {total_warning}")
    print(f"→ Gesamt Kompatibel: {total_compatible + total_warning}")
    print(f"Gelöste Felder: {total_resolved}")
    print(f"Aktion erforderlich: {total_needs_action}")
    print(f"GESAMT ALLE FELDER: {total_fields}")
    total_sum = total_compatible + total_warning + total_resolved + total_needs_action
    print(f"Berechnung: {total_compatible + total_warning} + {total_resolved} + "
          f"{total_needs_action} = {total_sum}")
    
    consistency_check = (total_compatible + total_warning + total_resolved + total_needs_action) == total_fields
    print(f"✅ Konsistenz-Check: {'BESTANDEN' if consistency_check else 'FEHLGESCHLAGEN'}")


if __name__ == "__main__":
    print("🧪 FILTER-KONSISTENZ TEST - NEUE VEREINFACHTE LOGIK")
    print("=" * 60)
    
    filter_ok = test_filter_consistency()
    test_detailed_breakdown_all_mappings()
    
    print("\n" + "=" * 60)
    if filter_ok:
        print("🎉 FILTER-TEST ERFOLGREICH!")
        print("   Die neuen Filter zeigen exakt die Zählungen der Status-Karten.")
        print("   Benutzer-Erfahrung: Konsistent und vorhersagbar!")
        print("   ALLE Mappings wurden erfolgreich getestet!")
    else:
        print("❌ FILTER-TEST FEHLGESCHLAGEN!")
        print("   Filter-Zählungen stimmen nicht mit Status-Karten überein.")
        print("   Siehe Details oben für spezifische Mappings.")
    print("=" * 60)
