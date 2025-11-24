# Fixed Value Automatic Detection

## Übersicht

Dieses Feature ermöglicht die automatische Erkennung und Übernahme von Fixed Values aus FHIR StructureDefinitions in den Mapping-Prozess.

## Architektur

Die Implementierung folgt dem Prinzip der Separation of Concerns und vermeidet Code-Duplikation durch dedizierte Klassen:

### 1. `fixed_value_extractor.py` - Zentrale Extraktions-Logik

**Verantwortlichkeit:** Extraktion aller Fixed Value Typen aus FHIR ElementDefinition

**Unterstützte Fixed Value Typen:**
- `fixedUri`
- `fixedUrl` 
- `fixedCanonical`
- `fixedString`
- `fixedCode`
- `fixedOid`
- `fixedId`
- `fixedUuid`
- `fixedInteger`
- `fixedDecimal`
- `fixedBoolean`
- `fixedDate`
- `fixedDateTime`
- `fixedTime`
- `fixedInstant`
- `patternCoding.system` (Spezialfall für .system Felder)

**Hauptmethoden:**
```python
FixedValueExtractor.extract_fixed_value(element)         # Extrahiert beliebigen fixed value
FixedValueExtractor.get_fixed_value_type(element)        # Gibt Typ zurück (z.B. 'fixedUri')
FixedValueExtractor.extract_pattern_coding_system(element) # Extrahiert patternCoding.system
FixedValueExtractor.has_fixed_or_pattern_value(element)  # Prüft Existenz
FixedValueExtractor.format_fixed_value_for_display(value) # Formatiert für UI
```

### 2. `profile.py` - ProfileField Properties

**Erweiterungen in der ProfileField Klasse:**
```python
@property
def fixed_value(self) -> Any | None:
    """Extrahiert jeden fixed* Wert aus dem ElementDefinition."""
    return FixedValueExtractor.extract_fixed_value(self.__data)

@property
def fixed_value_type(self) -> str | None:
    """Gibt den Typ des fixed value zurück."""
    return FixedValueExtractor.get_fixed_value_type(self.__data)

@property
def has_fixed_or_pattern(self) -> bool:
    """Prüft ob dieses Feld einen fixed oder pattern value hat."""
    return FixedValueExtractor.has_fixed_or_pattern_value(self.__data)

@property
def pattern_coding_system(self) -> str | None:
    """Extrahiert das system aus patternCoding."""
    return FixedValueExtractor.extract_pattern_coding_system(self.__data)
```

### 3. `mapping_actions_engine.py` - Automatische Detection

**Neue Funktion:** `_get_fixed_value_from_field()`

Erkennt automatisch Fixed Values aus dem Target-Profil und schlägt eine FIXED Action vor:

```python
def _get_fixed_value_from_field(field, target_key, all_fields) -> Optional[Any]:
    """Extract any fixed value from target field's profile.
    
    Checks for:
    1. Direct fixed values (fixedUri, fixedString, fixedCode, etc.)
    2. Pattern coding system for .system fields
    """
```

**Integration in `_inherit_or_default()`:**

Die Funktion wird in der Mapping Actions Engine aufgerufen, bevor andere Default-Actions gesetzt werden:

```python
# Check for any fixed value in target field
fixed_value = _get_fixed_value_from_field(field, target_key, all_fields)
if fixed_value is not None:
    return ActionInfo(
        action=ActionType.FIXED,
        source=ActionSource.SYSTEM_DEFAULT,
        auto_generated=True,
        system_remark="Auto-detected fixed value from target profile",
        fixed_value=fixed_value,
    )
```

## Funktionsweise

1. **Beim Laden eines Mappings** werden alle StructureDefinitions geparst
2. **ProfileField Objekte** lesen ElementDefinitions und stellen Fixed Values über Properties bereit
3. **Mapping Actions Engine** prüft automatisch, ob Target-Felder Fixed Values haben
4. **Wenn Fixed Value gefunden**: 
   - Action = `FIXED`
   - Source = `SYSTEM_DEFAULT`
   - `auto_generated = True`
   - `system_remark = "Auto-detected fixed value from target profile"`
5. **Manuelle Einträge** in `manual_entries.yaml` überschreiben automatisch erkannte Werte

## Beispiele

### Automatische Erkennung

StructureDefinition enthält:
```json
{
  "id": "MedicationRequest.extension:multiplePrescription.url",
  "path": "MedicationRequest.extension.url",
  "fixedUri": "https://gematik.de/fhir/epa-medication/StructureDefinition/multiple-prescription-extension"
}
```

Ergebnis im Mapping:
```yaml
- action: fixed
  fixed: "https://gematik.de/fhir/epa-medication/StructureDefinition/multiple-prescription-extension"
  name: MedicationRequest.extension:multiplePrescription.url
  auto_generated: true
  system_remark: "Auto-detected fixed value from target profile"
```

### Manuelle Überschreibung

Wenn in `manual_entries.yaml` ein anderer Wert definiert ist:
```yaml
- action: fixed
  fixed: "https://custom.url/example"
  name: MedicationRequest.extension:multiplePrescription.url
  remark: "Custom fixed value"
```

Dann wird der manuelle Eintrag verwendet (Manual überschreibt Auto-Detection).

## Tests

Die Implementierung ist vollständig testgetrieben entwickelt:

### Unit Tests
- `test_fixed_value_extractor.py` - 21 Tests für die Extraktions-Klasse
- Testet alle Fixed Value Typen
- Testet patternCoding Extraktion
- Testet Format-Funktionen

### Integration Tests
- `test_fixed_value_detection.py` - 9 Tests für die Integration
- Testet automatische Detection in der Mapping Engine
- Testet Priorität (Manual > Auto)
- Testet Spezialfälle (.system Felder)

### Alle Tests bestanden: 43/43 ✓

## Vorteile

✅ **Keine Code-Duplikation** - Zentrale FixedValueExtractor Klasse  
✅ **Saubere Architektur** - Klare Trennung der Verantwortlichkeiten  
✅ **Gut testbar** - Isolierte Komponenten mit umfassenden Tests  
✅ **Erweiterbar** - Neue Fixed Value Typen einfach hinzufügbar  
✅ **Wartbar** - Lesbare, strukturierte Implementierung  
✅ **Rückwärtskompatibel** - Manuelle Einträge haben Vorrang
