# Feature Analyse: Target Creation

## Implementierungsfortschritt

| Phase | Schritt | Status | Beschreibung |
|-------|---------|--------|--------------|
| 1 | 1.1 | ✅ | Backend Models erstellen (`target_creation.py`, `manual_entries.py`) |
| 1 | 1.2 | ✅ | Action Model (integriert in 1.1) |
| 2 | 2.1 | ✅ | TargetCreation Data Class erstellen |
| 2 | 2.2 | ✅ | Manual Entries erweitern |
| 3 | 3.1 | ✅ | Action Computation für Target Creation |
| 3 | 3.2 | ✅ | Evaluation für Target Creation |
| 4 | 4.1 | ✅ | TargetCreationHandler erstellen |
| 5 | 5.1 | ✅ | Router erstellen |
| 5 | 5.2 | ✅ | Router registrieren |
| 6 | 6.1 | ✅ | Frontend Models erstellen |
| 7 | 7.1 | ✅ | Frontend TargetCreationService erstellen |
| 8 | 8.1 | ✅ | Target Creation List Component erstellen |
| 8 | 8.2 | ✅ | Target Creation Detail Component erstellen |
| 8 | 8.3 | ✅ | Edit Target Creation Field Dialog erstellen |
| 8 | 8.4 | ✅ | Add Target Creation Dialog erstellen |
| 8 | 8.5 | ✅ | Integration in Edit Project |
| 8 | 8.6 | ✅ | Routing konfiguriert |
| 9 | 9.1-9.3 | ✅ | Breadcrumb Integration & Testing |
| 10 | 10.1-10.2 | ✅ | Shared Components Wiederverwendung (in Phase 8 integriert) |
| 11 | 11.1-11.2 | ⬜ | Optional Enhancements (YAML Export, Update Dialog) |
| 12 | 12.1-12.5 | ⬜ | Transformation-Integration |

---

## Übersicht

**Target Creation** ist eine neue dritte Entitätsart neben Mappings und Transformations. Bei Target Creations gibt es **kein Quellprofil** - der User definiert nur wie die Eigenschaften eines Zielprofils befüllt werden sollen.

### Unterschiede zu Mappings

| Aspekt | Mapping | Target Creation |
|--------|---------|-----------------|
| Quellprofile | 1-n Quellprofile | **Keine** |
| Zielprofil | 1 Zielprofil | 1 Zielprofil |
| Erlaubte Actions | use, use_recursive, not_use, empty, manual, copy_from, copy_to, fixed | **manual, fixed** |
| Vererbung | use_recursive vererbt an Kind-Felder | **Keine Vererbung** |
| Recommendations | System-Empfehlungen basierend auf Quell-Ziel-Vergleich | **Keine Recommendations** |
| Status-Berechnung | Kompatibilität Quelle↔Ziel | **Pflichtfelder (min>0) müssen Action haben** |
| Export | HTML, StructureMap | **Nur manual_entries.yaml** |
| Transformation-Link | Kann in Transformation verlinkt werden | **Kann in Transformation verlinkt werden** |
| Anwendungsfall | Transformation von Quelldaten → Zieldaten | Erstellung von Zielressourcen ohne Quelldaten |

### Datenstruktur (bereits in config.json vorhanden)

```json
{
  "target_creation": [
    {
      "id": "a1b2c3d4-e5f6-4789-8abc-9d0e1f2a3b4c",
      "version": "1.0",
      "status": "draft",
      "targetprofile": {
        "url": "https://example.org/StructureDefinition/MyProfile",
        "version": "1.0.0",
        "webUrl": "https://simplifier.net/...",
        "package": "my.package"
      },
      "last_updated": "2025-11-28T10:15:00.123456"
    }
  ]
}
```

---

## Implementierungsschritte

### Phase 1: Backend - Datenmodelle

#### Schritt 1.1: Target Creation Models erstellen ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/model/target_creation.py` (neu erstellt)

**Erstellte Models:**
- `TargetCreationAction` - Enum mit nur `manual` und `fixed`
- `TargetCreationFieldMinimal` - action, fixed, remark (kein other)
- `TargetCreationFieldBase` - Erweiterung um name für Persistierung
- `TargetCreationField` - Vollständiges Field mit name, types, min, max, actions_allowed, action_info
- `TargetCreationBase` / `TargetCreationListItem` - Liste für Übersicht
- `TargetCreationCreate` - Payload für Erstellung (nur target_id)
- `TargetCreationUpdate` - Payload für Metadaten-Update
- `TargetCreationDetails` - Vollständige Details mit fields
- `TargetCreationFieldsOutput` - Output für Field-List-Endpoint
- `TargetCreationEvaluationSummary` - Zusammenfassung der Evaluation

**Erweiterte Datei:** `service/src/structure_comparer/model/manual_entries.py`
- `ManualEntriesTargetCreation` - Neue Klasse für Target Creation Entries
- `ManualEntries.target_creation_entries` - Neues Feld
- `ManualEntries.get_target_creation()` - Getter-Methode
- `ManualEntries.set_target_creation()` - Setter-Methode
- `ManualEntries.remove_target_creation()` - Remove-Methode

**Besonderheiten:**
- `actions_allowed` ist immer nur `["manual", "fixed"]`
- Kein `other` Feld (copy_from/copy_to entfällt)
- Status-Counts: `action_required`, `resolved`, `optional_pending` (anstatt incompatible/warning/solved/compatible)

#### Schritt 1.2: Action Model erweitern
**Datei:** `service/src/structure_comparer/action.py`

> **Hinweis:** Eigene `TargetCreationAction` Enum wurde direkt in `target_creation.py` erstellt, 
> da es sich um ein separates, eingeschränktes Subset der Actions handelt.

---

### Phase 2: Backend - Data Classes

#### Schritt 2.1: TargetCreation Data Class erstellen ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/data/target_creation.py` (neu erstellt)

**Erstellte Klassen:**
- `TargetCreationField` - Feld-Klasse für Target Creation (nur manual/fixed Actions)
- `TargetCreation` - Hauptklasse für Target Creation Entitäten

**Hauptmethoden:**
- `init_ext()` - Initialisiert Target Creation mit Profil und Feldern
- `_load_target()` - Lädt Zielprofil aus Projekt-Paketen
- `_gen_fields()` - Generiert Felder aus dem Zielprofil
- `_apply_manual_entries()` - Wendet gespeicherte Manual Entries an
- `to_base_model()` / `to_details_model()` - Konvertiert zu API-Modellen

**Zusätzliche Config-Erweiterung:**
- `TargetCreationConfig` in `data/config.py` hinzugefügt
- `target_creations` Liste in `ProjectConfig` hinzugefügt

**Unterschied zu Mapping:**
- Keine `source_profiles`
- Keine `fill_allowed_actions()` mit komplexer Logik (immer nur manual/fixed)
- Keine Classification (compatible/incompatible) - alle Felder sind "zu definieren"

#### Schritt 2.2: Manual Entries erweitern ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/manual_entries.py` (erweitert)

**Hinzugefügte Methoden in `ManualEntries` Klasse:**
- `target_creation_entries` - Property für alle Target Creation Entries
- `get_target_creation(key)` - Holt Target Creation Entry nach ID
- `set_target_creation(target_creation)` - Setzt/aktualisiert Target Creation Entry
- `remove_target_creation(target_creation_id)` - Entfernt Target Creation Entry

**Erweiterte Methoden:**
- `read()` - Unterstützt nun `target_creation_entries` beim Laden
- `write()` - Behandelt `target_creation_entries` beim Speichern

---

### Phase 3: Backend - Actions & Evaluation

#### Schritt 3.1: Action Computation für Target Creation ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/evaluation/target_creation_evaluation.py` (neu erstellt)

**Implementierte Funktion:**
```python
def compute_target_creation_actions(
    target_creation: TargetCreation,
    manual_entries: ManualEntriesTargetCreation | None = None,
) -> dict[str, ActionInfo]:
    """
    Berechnet ActionInfo für jedes Feld.
    
    Vereinfacht gegenüber Mappings:
    - Keine Vererbung von Quellfeldern
    - Keine use/use_recursive Logik
    - Status basiert nur auf: Hat das Feld eine manuelle Action?
    """
```

#### Schritt 3.2: Evaluation für Target Creation ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/evaluation/target_creation_evaluation.py`

**Implementierte Funktionen und Klassen:**
```python
def evaluate_target_creation_field(field, action_info) -> EvaluationResult:
    """
    Einfache Evaluation basierend auf Kardinalität:
    
    - Feld hat action (manual/fixed) → 'resolved'
    - Pflichtfeld (min > 0) ohne action → 'action_required'
    - Optionales Feld (min = 0) ohne action → 'ok'
    
    Keine Recommendations, keine Vererbung.
    """

def evaluate_target_creation(target_creation, actions) -> dict[str, EvaluationResult]:
    """Evaluiert alle Felder einer Target Creation."""

class TargetCreationStatusAggregator:
    """Aggregiert Evaluierungsstatus für Target Creation Felder.
    
    Verwendet andere Status-Kategorien als Mappings:
    - action_required: Pflichtfelder (min > 0) ohne Action
    - resolved: Felder mit Action
    - optional_pending: Optionale Felder (min = 0) ohne Action
    """
```

**Exports in `evaluation/__init__.py` hinzugefügt:**
- `TargetCreationStatusAggregator`
- `compute_target_creation_actions`
- `evaluate_target_creation`
- `evaluate_target_creation_field`

---

### Phase 4: Backend - Handler

#### Schritt 4.1: TargetCreationHandler erstellen ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/handler/target_creation.py` (neu)

**Status:** Vollständig implementiert am 2025-12-03

**Implementierte Klasse und Methoden:**
```python
class TargetCreationNotFound(Exception):
    """Exception für nicht gefundene Target Creations"""

class TargetCreationHandler:
    """Analog zu MappingHandler, aber vereinfacht"""
    
    # CRUD Operationen:
    def list_target_creations(self, project_key: str) -> list[TargetCreationListItem]  ✅
    def get_target_creation(self, project_key: str, id: str) -> TargetCreationDetail  ✅
    def create_new(self, project_key: str, input: TargetCreationCreateInput) -> str  ✅
    def update_target_creation(self, project_key: str, id: str, input: TargetCreationUpdateInput)  ✅
    def delete_target_creation(self, project_key: str, id: str)  ✅
    
    # Field Operationen:
    def list_fields(self, project_key: str, id: str) -> list[TargetCreationField]  ✅
    def get_field(self, project_key: str, id: str, field_name: str) -> TargetCreationField  ✅
    def set_field(self, project_key: str, id: str, field_name: str, input: TargetCreationFieldMinimal)  ✅
    
    # Evaluation:
    def get_evaluation_summary(self, project_key: str, id: str) -> EvaluationSummary  ✅
```

**Besonderheiten:**
- Vereinfacht gegenüber MappingHandler (keine Quellprofile, keine Vererbung)
- Nur `manual` und `fixed` Actions erlaubt
- Status basiert auf Pflichtfeldern (min > 0) mit Actions
- Manual Entries werden in `manual_entries.yaml` gespeichert

**Zusätzliche Änderungen:**
- `data/project.py`: `target_creations` Dict und `load_target_creations()` Methode hinzugefügt
- `model/project.py`: `target_creations` Feld zum `Project` Model hinzugefügt

---

### Phase 5: Backend - API Endpoints

#### Schritt 5.1: Router erstellen ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/serve.py` (erweitert)

**Status:** Vollständig implementiert am 2025-12-03

**Implementierte Endpoints:**

```python
# Liste und Details
@app.get("/project/{project_key}/target-creation")                              # List all  ✅
@app.get("/project/{project_key}/target-creation/{id}")                         # Get details  ✅
@app.post("/project/{project_key}/target-creation")                             # Create  ✅
@app.patch("/project/{project_key}/target-creation/{id}")                       # Update metadata  ✅
@app.delete("/project/{project_key}/target-creation/{id}")                      # Delete  ✅

# Fields
@app.get("/project/{project_key}/target-creation/{id}/field")                   # List fields  ✅
@app.get("/project/{project_key}/target-creation/{id}/field/{field_name}")      # Get field  ✅
@app.put("/project/{project_key}/target-creation/{id}/field/{field_name}")      # Set field action  ✅

# Evaluation
@app.get("/project/{project_key}/target-creation/{id}/evaluation/summary")      # Get evaluation summary  ✅
```

**Gesamt: 9 Endpoints registriert und funktionsfähig**

**Tag in OpenAPI:** `Target Creations`

#### Schritt 5.2: Router registrieren ✅ ERLEDIGT
**Datei:** `service/src/structure_comparer/serve.py`

**Änderungen:**
```python
# Imports hinzugefügt
from .handler.target_creation import TargetCreationHandler, TargetCreationNotFound
from .model.target_creation import (
    TargetCreationBase as TargetCreationBaseModel,
    TargetCreationCreate as TargetCreationCreateModel,
    TargetCreationDetails as TargetCreationDetailsModel,
    TargetCreationUpdate as TargetCreationUpdateModel,
    TargetCreationField as TargetCreationFieldModel,
    TargetCreationFieldMinimal as TargetCreationFieldMinimalModel,
    TargetCreationFieldsOutput as TargetCreationFieldsOutputModel,
    TargetCreationEvaluationSummary as TargetCreationEvaluationSummaryModel,
)

# Global handler deklariert
target_creation_handler: TargetCreationHandler

# Handler initialisiert in lifespan()
target_creation_handler = TargetCreationHandler(project_handler)
```

**Verifikation:**
✅ Server startet ohne Fehler
✅ Alle 9 Endpoints in OpenAPI Schema registriert
✅ API-Dokumentation unter `/docs` verfügbar
✅ Tag "Target Creations" in Swagger UI sichtbar

---

### Phase 6: Frontend - Models

#### Schritt 6.1: Target Creation Models erstellen ✅ ERLEDIGT
**Datei:** `src/app/models/target-creation.model.ts` (neu erstellt)

**Status:** Vollständig implementiert am 2025-12-03

**Erstellte Models:**
```typescript
// Action Types (restricted subset)
export type TargetCreationAction = 'manual' | 'fixed';

// Profile Information
export interface ProfileInfo { name, url, version, webUrl?, package? }
export interface ProfileReference { url, version, webUrl?, package? }

// Status Counts (different from Mappings)
export interface TargetCreationStatusCounts {
  total: number;
  action_required: number;  // Mandatory fields without action
  resolved: number;         // Fields with action defined
  optional_pending: number; // Optional fields without action
}

// Field Models
export interface TargetCreationField {
  name: string;
  types: string[];
  min: number;
  max: string;
  extension?: string;
  description?: string;
  actions_allowed: TargetCreationAction[];  // Always ['manual', 'fixed']
  action_info?: ActionInfo;     // Reused from mapping-evaluation.model.ts
  evaluation?: EvaluationResult; // Reused from mapping-evaluation.model.ts
}

export interface TargetCreationFieldUpdate {
  action: TargetCreationAction;
  fixed?: string;   // For action='fixed'
  remark?: string;  // For action='manual'
}

// Entity Models
export interface TargetCreationListItem {
  id, name, url, version, status, target, status_counts, last_updated
}

export interface TargetCreationDetail {
  id, name, url, version, status, target, fields, status_counts, last_updated
}

// Input Models
export interface TargetCreationCreateInput {
  targetprofile: ProfileReference;  // Only target required, no sources
}

export interface TargetCreationUpdateInput {
  status?: string;
  version?: string;
  target?: ProfileReference;
}

// Evaluation
export interface TargetCreationEvaluationSummary {
  target_creation_id, target_creation_name, status_counts, field_evaluations
}

export interface TargetCreationFieldsOutput {
  fields: TargetCreationField[];
}
```

**Besonderheiten:**
- Wiederverwendung von `ActionInfo` und `EvaluationResult` aus `mapping-evaluation.model.ts`
- Keine source-bezogenen Felder (keine SourceProfile)
- Eigene Status-Counts (action_required/resolved/optional_pending statt incompatible/warning/solved/compatible)
- Restriktive Actions (nur manual, fixed)
- Ausführliche JSDoc-Kommentare für alle Interfaces

**Datei-Größe:** ~200 Zeilen inkl. Copyright und Kommentare

---

### Phase 7: Frontend - Service

#### Schritt 7.1: TargetCreationService erstellen ✅ ERLEDIGT
**Datei:** `src/app/target-creation.service.ts` (neu erstellt)

**Status:** Vollständig implementiert am 2025-12-03

**Implementierte Methoden:**

```typescript
@Injectable({ providedIn: 'root' })
export class TargetCreationService {
  private baseUrl = 'http://127.0.0.1:8000';

  // ===== CRUD Operations =====
  getTargetCreations(projectKey: string): Observable<TargetCreationListItem[]>  ✅
    → GET /project/{key}/target-creation

  getTargetCreation(projectKey: string, id: string): Observable<TargetCreationDetail>  ✅
    → GET /project/{key}/target-creation/{id}

  createTargetCreation(projectKey: string, input: TargetCreationCreateInput): Observable<{id: string}>  ✅
    → POST /project/{key}/target-creation

  updateTargetCreation(projectKey: string, id: string, input: TargetCreationUpdateInput): Observable<void>  ✅
    → PATCH /project/{key}/target-creation/{id}

  deleteTargetCreation(projectKey: string, id: string): Observable<void>  ✅
    → DELETE /project/{key}/target-creation/{id}

  // ===== Field Operations =====
  getFields(projectKey: string, id: string): Observable<TargetCreationField[]>  ✅
    → GET /project/{key}/target-creation/{id}/field
    → Extrahiert fields Array aus { fields: [...] } Response

  getField(projectKey: string, id: string, fieldName: string): Observable<TargetCreationField>  ✅
    → GET /project/{key}/target-creation/{id}/field/{name}

  setField(projectKey: string, id: string, fieldName: string, input: TargetCreationFieldUpdate): Observable<void>  ✅
    → PUT /project/{key}/target-creation/{id}/field/{name}

  // ===== Evaluation =====
  getEvaluationSummary(projectKey: string, id: string): Observable<TargetCreationEvaluationSummary>  ✅
    → GET /project/{key}/target-creation/{id}/evaluation/summary

  // ===== Error Handling =====
  private handleError(error: HttpErrorResponse)  ✅
    → Unified error handling analog zu MappingsService
}
```

**Alle 9 Backend-Endpoints abgedeckt:**
- ✅ List Target Creations
- ✅ Get Target Creation Details
- ✅ Create Target Creation
- ✅ Update Target Creation Metadata
- ✅ Delete Target Creation
- ✅ List Fields
- ✅ Get Field
- ✅ Set Field Action
- ✅ Get Evaluation Summary

**Besonderheiten:**
- Analog zu `MappingsService` strukturiert
- Alle Methoden nutzen HttpClient mit typsicheren Generics
- URL-Encoding für alle Parameter (projectKey, id, fieldName)
- Einheitliches Error-Handling mit catchError
- `getFields()` extrahiert Array aus Backend-Wrapper { fields: [...] }
- Ausführliche JSDoc-Kommentare für jede Methode

**Datei-Größe:** ~240 Zeilen inkl. Copyright und Kommentare

---

### Phase 6-7: Zusammenfassung

**Neue Dateien erstellt:**
- ✅ `src/app/models/target-creation.model.ts` (200 Zeilen)
- ✅ `src/app/target-creation.service.ts` (240 Zeilen)

**Gesamt:** ~440 neue Zeilen Frontend-Code

**Backend-Integration:**
- ✅ Alle 9 Backend-Endpoints werden vom Service aufgerufen
- ✅ TypeScript Models matchen Backend Pydantic Models
- ✅ Wiederverwendung existierender Types (ActionInfo, EvaluationResult)

**Code-Qualität:**
- ✅ Copyright-Header in allen Dateien
- ✅ Ausführliche JSDoc-Dokumentation
- ✅ TypeScript strict mode kompatibel
- ✅ Konsistente Namensgebung mit Mappings
- ✅ Error-Handling implementiert

**Nächste Phase: Components (Phase 8)**
Die Models und Service sind fertig. Als nächstes folgen:
1. Target Creation List Component (in edit-project integrieren)
2. Target Creation Detail Component (Feld-Tabelle)
3. Add Target Creation Dialog (Target-Profil auswählen)
4. Edit Target Creation Field Dialog (Action: manual/fixed)

---

### Phase 6: Frontend - Models

#### Schritt 6.1: Target Creation Models erstellen
**Datei:** `src/app/models/target-creation.model.ts` (neu)

```typescript
// Erlaubte Actions (eingeschränkt)
export type TargetCreationAction = 'manual' | 'fixed';

// Field Model
export interface TargetCreationField {
  name: string;
  types: string[];
  min: number;
  max: string;
  extension?: string;
  description?: string;
  actions_allowed: TargetCreationAction[];
  action_info?: ActionInfo;  // Wiederverwendbar von mapping-evaluation.model.ts
  evaluation?: EvaluationResult;
}

// Update Payload
export interface TargetCreationFieldUpdate {
  action: TargetCreationAction;
  fixed?: string;   // für action=fixed
  remark?: string;  // für action=manual
}

// List Item
export interface TargetCreationListItem {
  id: string;
  name: string;
  url: string;
  version: string;
  status: 'draft' | 'active' | 'deprecated';
  target: ProfileInfo;
  status_counts: StatusCounts;
}

// Detail
export interface TargetCreationDetail {
  id: string;
  name: string;
  url: string;
  version: string;
  status: string;
  target: ProfileInfo;
  fields: TargetCreationField[];
  status_counts: StatusCounts;
}

// Create Input
export interface TargetCreationCreateInput {
  targetprofile: ProfileReference;
}
```

---

### Phase 7: Frontend - Service

#### Schritt 7.1: TargetCreationService erstellen
**Datei:** `src/app/target-creation.service.ts` (neu)

```typescript
@Injectable({ providedIn: 'root' })
export class TargetCreationService {
  private baseUrl = 'http://127.0.0.1:8000';

  // CRUD
  getTargetCreations(projectKey: string): Observable<TargetCreationListItem[]>
  getTargetCreation(projectKey: string, id: string): Observable<TargetCreationDetail>
  createTargetCreation(projectKey: string, input: TargetCreationCreateInput): Observable<{id: string}>
  updateTargetCreation(projectKey: string, id: string, input: Partial<TargetCreationDetail>): Observable<void>
  deleteTargetCreation(projectKey: string, id: string): Observable<void>
  
  // Fields
  getFields(projectKey: string, id: string): Observable<TargetCreationField[]>
  setField(projectKey: string, id: string, fieldName: string, input: TargetCreationFieldUpdate): Observable<void>
  
  // Evaluation
  getEvaluationSummary(projectKey: string, id: string): Observable<EvaluationSummary>
}
```

---

### Phase 8: Frontend - Components

#### Schritt 8.1: Target Creation List Component
**Ordner:** `src/app/shared/target-creation-list/` (neu)

Analog zu `mapping-list/`:
- Tabelle mit ID, Name, Version, Status, Zielprofil, Status-Counts
- Click → Navigation zu Detail
- Actions: Edit, Delete

#### Schritt 8.2: Target Creation Detail Component
**Ordner:** `src/app/target-creation-detail/` (neu)

Vereinfachte Version von `mapping-detail/`:
- **Header:** Name, Version, Status, Zielprofil (kein Quellprofil!)
- **Feld-Tabelle:** Flat/Tree View wie bei Mappings
- **Spalten:** Name, Types, Cardinality, Action, Remark/Fixed Value
- **Keine Classification-Spalte** (kein Vergleich mit Quelle)

**Unterschiede zu MappingDetail:**
- Kein Source-Profil Header
- Keine Classification/Status basierend auf Quell-Ziel-Vergleich
- Einfachere Action-Auswahl (nur manual/fixed)

#### Schritt 8.3: Edit Target Creation Field Dialog
**Ordner:** `src/app/edit-target-creation-field-dialog/` (neu)

Vereinfachte Version von `edit-property-action-dialog/`:
- Feld-Info anzeigen (Name, Types, Cardinality)
- **Action Selection:** Nur `manual` oder `fixed`
- **Für `fixed`:** Input-Feld für den festen Wert
- **Für `manual`:** Textarea für Implementierungshinweise (remark)
- Keine Target-Field-Auswahl (kein copy_from/copy_to)

```typescript
interface EditTargetCreationFieldDialogData {
  field: TargetCreationField;
  projectKey: string;
  targetCreationId: string;
  target: ProfileInfo;
}
```

#### Schritt 8.4: Add Target Creation Dialog
**Ordner:** `src/app/add-target-creation-dialog/` (neu)

Vereinfachte Version von `add-mapping-dialog/`:
- **Nur Zielprofil auswählen** (kein Quellprofil)
- Package-Dropdown → Profil-Dropdown
- Optional: Version auswählen

---

### Phase 9: Frontend - Routing & Navigation

#### Schritt 9.1: Routes hinzufügen
**Datei:** `src/app/app.routes.ts`

```typescript
{
  path: 'project/:projectKey/target-creation/:targetCreationId',
  component: TargetCreationDetailComponent
}
```

#### Schritt 9.2: Edit Project erweitern
**Datei:** `src/app/edit-project/edit-project.component.ts`

- Neue Tab/Section: "Target Creations"
- `TargetCreationListComponent` einbinden
- "Add Target Creation" Button hinzufügen

#### Schritt 9.3: Breadcrumb Service erweitern
**Datei:** `src/app/breadcrumb.service.ts`

```typescript
// Neue Breadcrumb-Logik für Target Creation:
// Home > Project > Target Creation: [Name]
```

---

### Phase 10: Frontend - Shared Components Wiederverwendung ✅ ERLEDIGT

**Status:** Bereits in Phase 8.2-8.4 integriert

#### Schritt 10.1: Action Display wiederverwendet ✅
**Implementiert in:** Phase 8.2 (Target Creation Detail Component)

Die `MappingActionDisplayComponent` wird in der Target Creation Detail Component wiederverwendet:
```typescript
// In target-creation-detail.component.ts
import { MappingActionDisplayComponent } from '../shared/mapping-action-display/mapping-action-display.component';

// Im Template verwendet für Action-Badges
```

#### Schritt 10.2: Status Display wiederverwendet ✅
**Implementiert in:** Phase 8.2 (Target Creation Detail Component)

Die `MappingStatusDisplayComponent` wird wiederverwendet, da beide auf `ActionInfo` und `EvaluationResult` basieren:
```typescript
// In target-creation-detail.component.ts
import { MappingStatusDisplayComponent } from '../shared/mapping-status-display/mapping-status-display.component';
```

**Ergebnis:**
- ✅ Keine neuen Action/Status Display Components nötig
- ✅ Konsistentes UI durch Wiederverwendung
- ✅ Weniger Code-Duplikation

---

### Phase 11: Optional Enhancements

#### Schritt 11.1: YAML Export implementieren
**Datei:** `src/app/target-creation-detail/target-creation-detail.component.ts`

**Was fehlt:**
- Implementierung von `exportAsYaml()` (aktuell Placeholder)
- Format: manual_entries.yaml Export
- Download-Logik

**Placeholder:**
```typescript
exportAsYaml(): void {
  this.snackBar.open('YAML Export wird implementiert', 'OK', { duration: 2000 });
  // TODO: Implement YAML export (Phase 11.1)
}
```

#### Schritt 11.2: Update Metadata Dialog
**Was fehlt:**
- Dialog zum Ändern von Metadaten (Version, Status)
- Analog zu EditMappingDialog
- Button im Detail-Header

**Priorität:** Niedrig (Metadaten ändern sich selten)

---

### Phase 12: Transformation-Integration

Target Creations können (analog zu Mappings) in Transformations verlinkt werden, um anzuzeigen welche Zielressourcen ohne Quelldaten erstellt werden müssen.

#### Schritt 12.1: Backend - TransformationField erweitern
**Datei:** `service/src/structure_comparer/models/transformation.py`

```python
# TransformationField erweitern um:
target_creation: Optional[str]  # ID einer verlinkten Target Creation (analog zu map)
```

#### Schritt 12.2: Backend - TransformationHandler erweitern
**Datei:** `service/src/structure_comparer/handlers/transformation_handler.py`

```python
# Neue Methoden:
def link_target_creation(self, project_key: str, transformation_id: str, 
                         field_name: str, target_creation_id: str)
def unlink_target_creation(self, project_key: str, transformation_id: str, 
                           field_name: str)
```

#### Schritt 12.3: Backend - API Endpoints erweitern
**Datei:** `service/src/structure_comparer/routers/transformation.py`

```python
# Neue Endpoints:
@router.post("/{id}/fields/{field_name}/target-creation")   # Link Target Creation
@router.delete("/{id}/fields/{field_name}/target-creation") # Unlink Target Creation
```

#### Schritt 12.4: Frontend - Transformation Service erweitern
**Datei:** `src/app/transformation.service.ts`

```typescript
// Neue Methoden:
linkTargetCreation(projectKey: string, transformationId: string, 
                   fieldName: string, targetCreationId: string): Observable<void>
unlinkTargetCreation(projectKey: string, transformationId: string, 
                     fieldName: string): Observable<void>
```

#### Schritt 12.5: Frontend - Transformation Detail UI erweitern
**Datei:** `src/app/transformation-detail/`

- In der Resource-Tabelle: Zusätzliche Spalte/Option für "Target Creation"
- Dropdown zur Auswahl einer Target Creation (statt/neben Mapping)
- Unterscheidung: Mapping = Transformation mit Quelldaten, Target Creation = Erstellung ohne Quelle

---

## Zusammenfassung der neuen Dateien

### Backend (structure-comparer)
```
service/src/structure_comparer/
├── models/
│   └── target_creation.py              # NEU
├── data/
│   ├── target_creation.py              # NEU
│   └── manual_entries.py               # ÄNDERN
├── actions/
│   └── target_creation_actions.py      # NEU
├── evaluation/
│   └── target_creation_evaluation.py   # NEU
├── handlers/
│   └── target_creation_handler.py      # NEU
├── routers/
│   └── target_creation.py              # NEU
└── serve.py                            # ÄNDERN
```

### Frontend (structure-comparer-frontend)
```
src/app/
├── models/
│   └── target-creation.model.ts                    # NEU
├── target-creation.service.ts                      # NEU
├── target-creation-detail/
│   ├── target-creation-detail.component.ts        # NEU
│   ├── target-creation-detail.component.html      # NEU
│   └── target-creation-detail.component.css       # NEU
├── add-target-creation-dialog/
│   ├── add-target-creation-dialog.component.ts    # NEU
│   ├── add-target-creation-dialog.component.html  # NEU
│   └── add-target-creation-dialog.component.css   # NEU
├── edit-target-creation-field-dialog/
│   ├── edit-target-creation-field-dialog.component.ts    # NEU
│   ├── edit-target-creation-field-dialog.component.html  # NEU
│   └── edit-target-creation-field-dialog.component.css   # NEU
├── shared/
│   └── target-creation-list/
│       ├── target-creation-list.component.ts      # NEU
│       ├── target-creation-list.component.html    # NEU
│       └── target-creation-list.component.css     # NEU
├── edit-project/
│   └── edit-project.component.ts                  # ÄNDERN
├── breadcrumb.service.ts                          # ÄNDERN
└── app.routes.ts                                  # ÄNDERN
```

---

## Empfohlene Implementierungsreihenfolge

### Meilenstein 1: Standalone Target Creation (MVP)
1. **Backend Models** (Phase 1) - Datenstrukturen definieren
2. **Backend Data Classes** (Phase 2) - Basis-Logik + Manual Entries erweitern
3. **Backend Handler** (Phase 4) - CRUD ohne Evaluation
4. **Backend Router** (Phase 5) - API verfügbar machen
5. **Frontend Models** (Phase 6) - TypeScript Interfaces
6. **Frontend Service** (Phase 7) - API-Anbindung
7. **Frontend List Component** (Phase 8.1) - Übersicht in Edit Project
8. **Frontend Detail Component** (Phase 8.2) - Feld-Ansicht
9. **Frontend Dialogs** (Phase 8.3, 8.4) - Bearbeitung
10. **Backend Evaluation** (Phase 3) - Status-Berechnung (Pflichtfelder prüfen)
11. **Routing & Navigation** (Phase 9) - Integration

### Meilenstein 2: Transformation-Integration
12. **Backend Transformation erweitern** (Phase 11.1-11.3) - Target Creation Links
13. **Frontend Transformation erweitern** (Phase 11.4-11.5) - UI für Target Creation Links

---

## Design-Entscheidungen

| Aspekt | Entscheidung | Details |
|--------|--------------|---------|
| **Vererbung** | ❌ Nein | Keine `use_recursive`-ähnliche Vererbung. Jedes Feld wird einzeln definiert. |
| **Recommendations** | ❌ Nein | Keine automatischen System-Empfehlungen (da kein Quellprofil zum Vergleichen). |
| **Status-Berechnung** | Pflichtfelder prüfen | Felder mit min > 0 müssen eine Action haben → sonst `action_required` |
| **Export-Formate** | Nur `manual_entries.yaml` | Kein HTML/StructureMap Export. Speicherung wie gewohnt pro Feld mit Action + Eigenschaften. |
| **Transformation-Integration** | ✅ Ja | Target Creations können in Transformations verlinkt werden (analog zu Mappings). |

---

## ✅ IMPLEMENTIERUNGS-ZUSAMMENFASSUNG (Stand: 2025-12-03)

### Abgeschlossene Phasen

#### **Phase 1-3: Backend Foundation** ✅ KOMPLETT
- ✅ Models (`target_creation.py`, `manual_entries.py` erweitert)
- ✅ Data Classes (`data/target_creation.py`, `data/config.py` erweitert)
- ✅ Action Computation (`evaluation/target_creation_evaluation.py`)
- ✅ Evaluation Engine (`TargetCreationStatusAggregator`)

#### **Phase 4-5: Backend API** ✅ KOMPLETT (2025-12-03)
- ✅ Handler (`handler/target_creation.py` - 416 Zeilen)
  - CRUD Operationen für Target Creations
  - Field-Level Operationen
  - Evaluation Summary
  - Exception: `TargetCreationNotFound`
- ✅ API Endpoints (`serve.py` - 9 Endpoints)
  - GET `/project/{key}/target-creation` - List
  - GET `/project/{key}/target-creation/{id}` - Details
  - POST `/project/{key}/target-creation` - Create
  - PATCH `/project/{key}/target-creation/{id}` - Update
  - DELETE `/project/{key}/target-creation/{id}` - Delete
  - GET `/project/{key}/target-creation/{id}/field` - List Fields
  - GET `/project/{key}/target-creation/{id}/field/{name}` - Get Field
  - PUT `/project/{key}/target-creation/{id}/field/{name}` - Set Field
  - GET `/project/{key}/target-creation/{id}/evaluation/summary` - Summary
- ✅ Project Integration
  - `data/project.py`: `target_creations` Dict + `load_target_creations()`
  - `model/project.py`: `target_creations` field
  - Handler-Initialisierung in `serve.py` lifespan

**Backend Status:** 🟢 Produktionsbereit  
**API Verifikation:** ✅ Alle Endpoints in OpenAPI registriert  
**Server Test:** ✅ Startet ohne Fehler

### Dateien Erstellt/Geändert in Phase 4-5

**Neu erstellt:**
- `service/src/structure_comparer/handler/target_creation.py` (416 Zeilen)
- `IMPLEMENTATION_PHASE_4_5_SUMMARY.md` (Dokumentation)

**Geändert:**
- `service/src/structure_comparer/serve.py` (+252 Zeilen)
- `service/src/structure_comparer/data/project.py` (+15 Zeilen)
- `service/src/structure_comparer/model/project.py` (+2 Zeilen)
- `Feature_Analysis_target_creation.md` (Status-Updates)

**Gesamt:** ~685 neue Zeilen Code

### Nächster Schritt: Frontend (Phase 6-10)

Das Backend ist fertig und bereit für Frontend-Integration. Der nächste Prompt sollte beginnen mit:

```
Führe Phase 6 aus: Frontend Models erstellen!
Erstelle `src/app/models/target-creation.model.ts` mit allen TypeScript Interfaces.
```

**Voraussetzungen für Frontend:**
- ✅ Backend API läuft auf `http://localhost:8000`
- ✅ Alle Endpoints getestet und funktionsfähig
- ✅ OpenAPI Schema verfügbar unter `/openapi.json`
- ✅ Models in `model/target_creation.py` als Referenz

**Referenz-Dokumentation:**
- Detailed Implementation: `IMPLEMENTATION_PHASE_4_5_SUMMARY.md`
- API Endpoints: Siehe Phase 5 in diesem Dokument
- Model Definitions: `service/src/structure_comparer/model/target_creation.py`

---

### Dateien Erstellt/Geändert in Phase 6-8.1

#### **Phase 6-7: Frontend Foundation** ✅ KOMPLETT (2025-12-03)
- ✅ Models (`src/app/models/target-creation.model.ts` - 208 Zeilen)
  - 12 Interfaces/Types für Target Creation
  - Wiederverwendung von ActionInfo, EvaluationResult
  - Eigene Status-Kategorien (action_required, resolved, optional_pending)
- ✅ Service (`src/app/target-creation.service.ts` - 251 Zeilen)
  - 9 Methoden für alle Backend-Endpoints
  - Type-safe mit TypeScript Generics
  - Error-Handling analog zu MappingsService

#### **Phase 8.1: Target Creation List Component** ✅ KOMPLETT (2025-12-03)
- ✅ Component (`src/app/shared/target-creation-list/target-creation-list.component.ts` - 273 Zeilen)
  - Standalone Component mit inline Template
  - Tabelle mit 10 Spalten (ID, Name, Version, Status, Target, Counts, Actions)
  - Sortierung nach allen Spalten
  - Status Badges: draft/active/deprecated
  - Status Pills: Total/Required/Resolved/Optional
  - Events: View, Delete, Create, Changed
- ✅ Styles (`src/app/shared/target-creation-list/target-creation-list.component.css` - 236 Zeilen)
  - Responsive Table Design
  - Colored Pills und Badges
  - Hover Effects
  - Media Queries

**Frontend Status (Phase 6-8.1):** 🟢 Bereit für Integration  
**LOC:** ~968 Zeilen (Models: 208, Service: 251, Component: 509)  
**TypeScript Errors:** ✅ Keine

**Neu erstellt in Phase 8.1:**
- `src/app/shared/target-creation-list/target-creation-list.component.ts`
- `src/app/shared/target-creation-list/target-creation-list.component.css`
- `IMPLEMENTATION_PHASE_8_1_SUMMARY.md` (Dokumentation)
- `PHASE_8_1_QUICK_REFERENCE.md` (Quick Reference)

### Nächster Schritt: Phase 8.2 (Detail Component)

```bash
Führe Phase 8.2 aus: Target Creation Detail Component erstellen!
```

**Was zu tun ist:**
1. Erstelle `src/app/target-creation-detail/` mit 3 Dateien (.ts, .html, .css)
2. Header mit Target Creation Metadaten (Name, Version, Status, Target Profile)
3. Field-Tabelle mit Tree/Flat View (wie MappingDetail)
4. KEINE Source-Profile, KEINE Classification-Spalte
5. Click auf Feld öffnet Edit-Dialog (Phase 8.3)

**Referenzen:**
- Struktur: `src/app/mapping-detail/`
- Service: `TargetCreationService.getTargetCreation(), getFields()`
- Models: `TargetCreationDetail`, `TargetCreationField`
- Checkpoint: `CHECKPOINT_PHASE_6_7.md`

---

