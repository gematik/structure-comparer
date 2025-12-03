# Target Creation - Quick Start Guide für Phase 6+

**Stand:** 2025-12-03  
**Status Backend:** ✅ Komplett (Phase 1-5)  
**Nächster Schritt:** Frontend Models (Phase 6)

---

## Was wurde bereits implementiert?

### ✅ Backend (Komplett)

1. **Models** - Pydantic Models für API
   - Datei: `service/src/structure_comparer/model/target_creation.py`
   - Enthält: Actions, Fields, Create/Update/Details Models

2. **Data Classes** - Business Logic
   - Datei: `service/src/structure_comparer/data/target_creation.py`
   - Klassen: `TargetCreation`, `TargetCreationField`

3. **Evaluation** - Status Berechnung
   - Datei: `service/src/structure_comparer/evaluation/target_creation_evaluation.py`
   - Status: `action_required`, `resolved`, `optional_pending`

4. **Handler** - CRUD Operations
   - Datei: `service/src/structure_comparer/handler/target_creation.py`
   - 9 Methoden: list, get, create, update, delete, fields, set_field, evaluation

5. **API Endpoints** - REST API
   - Datei: `service/src/structure_comparer/serve.py`
   - 9 Endpoints unter `/project/{key}/target-creation/...`

6. **Project Integration**
   - Target Creations werden beim Projekt-Load geladen
   - In config.json gespeichert
   - Manual entries in manual_entries.yaml

---

## API Endpunkte (alle funktionsfähig)

```
Base URL: http://localhost:8000

GET    /project/{key}/target-creation                     → Liste
GET    /project/{key}/target-creation/{id}                → Details
POST   /project/{key}/target-creation                     → Erstellen
PATCH  /project/{key}/target-creation/{id}                → Aktualisieren
DELETE /project/{key}/target-creation/{id}                → Löschen

GET    /project/{key}/target-creation/{id}/field          → Alle Felder
GET    /project/{key}/target-creation/{id}/field/{name}   → Ein Feld
PUT    /project/{key}/target-creation/{id}/field/{name}   → Feld setzen

GET    /project/{key}/target-creation/{id}/evaluation/summary → Status-Übersicht
```

**OpenAPI Docs:** http://localhost:8000/docs (Tag: "Target Creations")

---

## Nächste Phase: Frontend Models (Phase 6)

### Aufgabe
Erstelle TypeScript Interfaces in `src/app/models/target-creation.model.ts`

### Benötigte Models

```typescript
// Actions (nur manual & fixed!)
export type TargetCreationAction = 'manual' | 'fixed';

// Field Models
export interface TargetCreationField { ... }
export interface TargetCreationFieldUpdate { ... }

// Entity Models
export interface TargetCreationListItem { ... }
export interface TargetCreationDetail { ... }

// Input Models
export interface TargetCreationCreateInput { ... }
export interface TargetCreationUpdateInput { ... }

// Evaluation
export interface TargetCreationEvaluationSummary { ... }
```

### Referenzen

**Backend Models als Vorlage:**
- `service/src/structure_comparer/model/target_creation.py`

**Ähnliche Mapping Models zum Vergleich:**
- `src/app/models/mapping.model.ts`
- `src/app/models/mapping-evaluation.model.ts`

**Wiederverwendbare Types:**
- `ActionInfo` - aus `mapping-evaluation.model.ts`
- `EvaluationResult` - aus `mapping-evaluation.model.ts`
- `ProfileInfo` - aus existierenden Models

---

## Key Unterschiede zu Mappings

| Feature | Mapping | Target Creation |
|---------|---------|-----------------|
| **Quellprofile** | Ja (1-n) | ❌ Nein |
| **Actions** | use, use_recursive, manual, fixed, copy_from, copy_to | **Nur manual, fixed** |
| **Vererbung** | Ja | ❌ Nein |
| **Recommendations** | Ja | ❌ Nein |
| **Status Counts** | incompatible, warning, solved, compatible | **action_required, resolved, optional_pending** |
| **Classification** | Basiert auf Quell-Ziel-Vergleich | ❌ Nicht vorhanden |

---

## Prompt-Vorlage für Phase 6

```
Führe Phase 6 aus: Frontend Models erstellen!

Erstelle `src/app/models/target-creation.model.ts` mit folgenden Interfaces:

1. TargetCreationAction (Type: 'manual' | 'fixed')
2. TargetCreationField (vollständiges Feld mit action_info und evaluation)
3. TargetCreationFieldUpdate (Payload für PUT /field/{name})
4. TargetCreationListItem (für Listen-Ansicht)
5. TargetCreationDetail (mit allen Feldern)
6. TargetCreationCreateInput (nur target_id benötigt)
7. TargetCreationUpdateInput (status, version, target optional)
8. TargetCreationEvaluationSummary (Status-Counts)

Orientiere dich an:
- Backend Model: service/src/structure_comparer/model/target_creation.py
- Ähnliche Models: src/app/models/mapping.model.ts

Wichtig: 
- Wiederverwendung von ActionInfo und EvaluationResult aus mapping-evaluation.model.ts
- Keine source-bezogenen Felder
- Status counts: action_required, resolved, optional_pending
```

---

## Danach: Phase 7-10

Nach den Models folgt:

7. **Service** (`target-creation.service.ts`)
   - HTTP-Aufrufe zu allen 9 Endpoints
   - Analog zu `mapping.service.ts`

8. **Components**
   - List Component (in edit-project einbinden)
   - Detail Component (Feld-Tabelle)
   - Field Dialog (Action auswählen: manual/fixed)
   - Create Dialog (nur Target-Profil auswählen)

9. **Routing**
   - Route zu Detail-Component
   - Breadcrumbs erweitern

10. **Integration**
    - Tab in Edit Project
    - Navigation von Liste zu Detail

---

## Hilfreiche Befehle

```bash
# Backend neu starten
cd /Users/Shared/dev/structure-comparer
.venv/bin/python -m uvicorn src.structure_comparer.serve:app --reload

# Frontend starten
cd /Users/Shared/dev/structure-comparer-frontend
npm start

# API testen
curl http://localhost:8000/project/{key}/target-creation

# OpenAPI Schema
curl http://localhost:8000/openapi.json | jq '.paths | keys[] | select(contains("target-creation"))'
```

---

## Dokumentation

- **Feature Analyse:** `Feature_Analysis_target_creation.md`
- **Phase 4-5 Summary:** `IMPLEMENTATION_PHASE_4_5_SUMMARY.md`
- **Backend Models:** `service/src/structure_comparer/model/target_creation.py`

---

## Status-Übersicht

| Phase | Status | Beschreibung |
|-------|--------|--------------|
| 1 | ✅ | Backend Models |
| 2 | ✅ | Backend Data Classes |
| 3 | ✅ | Backend Evaluation |
| 4 | ✅ | Backend Handler |
| 5 | ✅ | Backend API Endpoints |
| **6** | **⬜ NÄCHSTER SCHRITT** | **Frontend Models** |
| 7 | ⬜ | Frontend Service |
| 8 | ⬜ | Frontend Components |
| 9 | ⬜ | Frontend Routing |
| 10 | ⬜ | Frontend Integration |
| 11 | ⬜ | Transformation Links |

**Backend:** 🟢 Produktionsbereit  
**Frontend:** ⚪ Bereit zum Start

---

Viel Erfolg bei der Frontend-Implementierung! 🚀
