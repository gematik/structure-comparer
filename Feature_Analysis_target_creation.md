# Feature Analyse: Target Creation

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

#### Schritt 1.1: Target Creation Models erstellen
**Datei:** `service/src/structure_comparer/models/target_creation.py` (neu)

```python
# Zu erstellende Models:
- TargetCreationFieldMinimal  # action, fixed, remark (kein other, da kein copy)
- TargetCreationFieldManualEntry  # für manual_entries.yaml
- TargetCreationField  # Vollständiges Field mit name, types, min, max, actions_allowed, action_info
- TargetCreationListItem  # Liste für Übersicht (id, name, url, version, status, status_counts)
- TargetCreationCreateInput  # Payload für Erstellung (nur targetprofile)
- TargetCreationUpdateInput  # Payload für Metadaten-Update
- TargetCreationDetail  # Vollständige Details mit fields
```

**Besonderheiten:**
- `actions_allowed` ist immer nur `["manual", "fixed"]`
- Kein `other` Feld (copy_from/copy_to entfällt)
- `action_info` vereinfacht (keine source-bezogenen Informationen)

#### Schritt 1.2: Action Model erweitern
**Datei:** `service/src/structure_comparer/models/action.py`

```python
# Neue Enum-Werte oder separates Enum für erlaubte Actions:
class TargetCreationAction(StrEnum):
    MANUAL = "manual"
    FIXED = "fixed"
```

---

### Phase 2: Backend - Data Classes

#### Schritt 2.1: TargetCreation Data Class erstellen
**Datei:** `service/src/structure_comparer/data/target_creation.py` (neu)

```python
# Zu implementierende Klasse:
@dataclass
class TargetCreation:
    id: str
    version: str
    status: str
    target_profile: Profile
    fields: list[TargetCreationField]
    
    def load_fields(self, target_profile_data):
        """Lädt alle Felder aus dem Zielprofil"""
        
    def fill_allowed_actions(self):
        """Setzt actions_allowed = [MANUAL, FIXED] für alle Felder"""
```

**Unterschied zu Mapping:**
- Keine `source_profiles`
- Keine `fill_allowed_actions()` mit komplexer Logik (immer nur manual/fixed)
- Keine Classification (compatible/incompatible) - alle Felder sind "zu definieren"

#### Schritt 2.2: Manual Entries erweitern
**Datei:** `service/src/structure_comparer/data/manual_entries.py`

```python
# Erweitern um:
- target_creation_entries: list[TargetCreationManualEntry]

# In ManualEntriesFile:
def get_target_creation_entries(self, target_creation_id: str) -> list[...]
def set_target_creation_entry(self, target_creation_id: str, field: ...)
```

---

### Phase 3: Backend - Actions & Evaluation

#### Schritt 3.1: Action Computation für Target Creation
**Datei:** `service/src/structure_comparer/actions/target_creation_actions.py` (neu)

```python
def compute_target_creation_actions(
    target_creation: TargetCreation,
    manual_entries: list[TargetCreationFieldManualEntry]
) -> list[TargetCreationField]:
    """
    Berechnet ActionInfo für jedes Feld.
    
    Vereinfacht gegenüber Mappings:
    - Keine Vererbung von Quellfeldern
    - Keine use/use_recursive Logik
    - Status basiert nur auf: Hat das Feld eine manuelle Action?
    """
```

#### Schritt 3.2: Evaluation für Target Creation
**Datei:** `service/src/structure_comparer/evaluation/target_creation_evaluation.py` (neu)

```python
def evaluate_target_creation_field(field: TargetCreationField) -> EvaluationResult:
    """
    Einfache Evaluation basierend auf Kardinalität:
    
    - Feld hat action (manual/fixed) → 'resolved'
    - Pflichtfeld (min > 0) ohne action → 'action_required'
    - Optionales Feld (min = 0) ohne action → 'ok'
    
    Keine Recommendations, keine Vererbung.
    """
```

---

### Phase 4: Backend - Handler

#### Schritt 4.1: TargetCreationHandler erstellen
**Datei:** `service/src/structure_comparer/handlers/target_creation_handler.py` (neu)

```python
class TargetCreationHandler:
    """Analog zu MappingHandler, aber vereinfacht"""
    
    # CRUD Operationen:
    def list_target_creations(self, project_key: str) -> list[TargetCreationListItem]
    def get_target_creation(self, project_key: str, id: str) -> TargetCreationDetail
    def create_target_creation(self, project_key: str, input: TargetCreationCreateInput) -> str
    def update_target_creation(self, project_key: str, id: str, input: TargetCreationUpdateInput)
    def delete_target_creation(self, project_key: str, id: str)
    
    # Field Operationen:
    def list_fields(self, project_key: str, id: str) -> list[TargetCreationField]
    def get_field(self, project_key: str, id: str, field_name: str) -> TargetCreationField
    def set_field(self, project_key: str, id: str, field_name: str, input: TargetCreationFieldMinimal)
    
    # Evaluation:
    def get_evaluation_summary(self, project_key: str, id: str) -> EvaluationSummary
```

---

### Phase 5: Backend - API Endpoints

#### Schritt 5.1: Router erstellen
**Datei:** `service/src/structure_comparer/routers/target_creation.py` (neu)

```python
router = APIRouter(prefix="/projects/{project_key}/target-creations", tags=["Target Creations"])

# Endpoints:
@router.get("/")                           # List all
@router.get("/{id}")                       # Get details
@router.post("/")                          # Create
@router.patch("/{id}")                     # Update metadata
@router.delete("/{id}")                    # Delete

@router.get("/{id}/fields")                # List fields
@router.get("/{id}/fields/{field_name}")   # Get field
@router.post("/{id}/fields/{field_name}")  # Set field action

@router.get("/{id}/evaluation/summary")    # Get evaluation summary
```

#### Schritt 5.2: Router registrieren
**Datei:** `service/src/structure_comparer/serve.py`

```python
from .routers import target_creation
app.include_router(target_creation.router)
```

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

### Phase 10: Frontend - Shared Components Anpassen

#### Schritt 10.1: Action Selection anpassen
**Datei:** `src/app/edit-property-action-dialog/action-selection/`

Option A: Generisch machen mit Input für erlaubte Actions
Option B: Separate `TargetCreationActionSelection` Component

#### Schritt 10.2: Status Display wiederverwenden
Die Components `mapping-status-display` und `mapping-action-display` können wiederverwendet werden, da sie auf `ActionInfo` basieren.

---

### Phase 11: Transformation-Integration

Target Creations können (analog zu Mappings) in Transformations verlinkt werden, um anzuzeigen welche Zielressourcen ohne Quelldaten erstellt werden müssen.

#### Schritt 11.1: Backend - TransformationField erweitern
**Datei:** `service/src/structure_comparer/models/transformation.py`

```python
# TransformationField erweitern um:
target_creation: Optional[str]  # ID einer verlinkten Target Creation (analog zu map)
```

#### Schritt 11.2: Backend - TransformationHandler erweitern
**Datei:** `service/src/structure_comparer/handlers/transformation_handler.py`

```python
# Neue Methoden:
def link_target_creation(self, project_key: str, transformation_id: str, 
                         field_name: str, target_creation_id: str)
def unlink_target_creation(self, project_key: str, transformation_id: str, 
                           field_name: str)
```

#### Schritt 11.3: Backend - API Endpoints erweitern
**Datei:** `service/src/structure_comparer/routers/transformation.py`

```python
# Neue Endpoints:
@router.post("/{id}/fields/{field_name}/target-creation")   # Link Target Creation
@router.delete("/{id}/fields/{field_name}/target-creation") # Unlink Target Creation
```

#### Schritt 11.4: Frontend - Transformation Service erweitern
**Datei:** `src/app/transformation.service.ts`

```typescript
// Neue Methoden:
linkTargetCreation(projectKey: string, transformationId: string, 
                   fieldName: string, targetCreationId: string): Observable<void>
unlinkTargetCreation(projectKey: string, transformationId: string, 
                     fieldName: string): Observable<void>
```

#### Schritt 11.5: Frontend - Transformation Detail UI erweitern
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
