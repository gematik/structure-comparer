Instance: ERPTPrescriptionStructureMapMedicationRequest
InstanceOf: StructureMap
Usage: #definition
Title: "E-T-Rezept Structure Map for MedicationRequest"
Description: "Mapping-Anweisungen zur Transformation von KBV MedicationRequest zu BfArM T-Prescription MedicationRequest"
* insert Instance(StructureMap, ERPTPrescriptionStructureMapMedicationRequest)
* insert sd_structure(https://fhir.kbv.de/StructureDefinition/KBV_PR_ERP_Prescription, source, kbvMedicationRequest)
* insert sd_structure(https://gematik.de/fhir/erp-t-prescription/StructureDefinition/erp-tprescription-medication-request, target, bfarmMedicationRequest)

* group[+]
  * name = "ERPTPrescriptionStructureMapMedicationRequest"
  * typeMode = #none
  * documentation = "Mapping-Anweisungen zur Transformation von KBV MedicationRequest zu BfArM T-Prescription MedicationRequest"

  * insert sd_input(kbvMedicationRequest, source)
  * insert sd_input(bfarmMedicationRequest, target)

  // set status to completed
  * rule[+]
    * name = "medicationRequestStatus"
    * insert treeSource(kbvMedicationRequest, status, srcStatus)
    * insert targetSetStringVariable(bfarmMedicationRequest, status, completed)
    * documentation = "Setzt den Status auf 'completed' für den digitalen Durchschlag (Verschreibung ist bereits abgeschlossen)"

  // set intent to order
  * rule[+]
    * name = "medicationRequestIntent"
    * source.context = "kbvMedicationRequest"
    * source.element = "intent"
    * insert targetSetStringVariable(bfarmMedicationRequest, intent, order)
    * documentation = "Setzt den Intent auf 'order' entsprechend der BfArM-Spezifikation für T-Prescription"

  //Copy T-Prescription Extensions
  * rule[+]
    * name = "medicationRequestExt"
    * documentation = "Mappt T-Rezept spezifische Extensions vom KBV- zum BfArM-Format"
    * insert treeSource(kbvMedicationRequest, extension, extVar)
    * insert treeTarget(bfarmMedicationRequest, extension, tgtExtVar)
    * rule[+]
      * name = "copyTPrescriptionExtensionUrl"
      * documentation = "Kopiert teratogene Extensions für T-Rezept Kennzeichnung"
      * source[+].context = "extVar"
      * source[=].variable = "extMatchVar"
      * source[=].condition = "url='https://fhir.kbv.de/StructureDefinition/KBV_EX_ERP_Teratogenic'"
      * insert targetSetStringVariable(tgtExtVar, url,  https://fhir.kbv.de/StructureDefinition/KBV_EX_ERP_Teratogenic)
      * rule[+]
        * name = "copyExtensionValue"
        * documentation = "Übernimmt den Wert der teratogenen Extension unverändert"
        * insert treeSource(extMatchVar, extension, extValVar)
        * insert targetSetIdVariable(tgtExtVar, extension, extValVar)

  // set subject to not-permitted
  * rule[+]
    * name = "medicationRequestsubject"
    * documentation = "Entfernt Patientenbezug durch data-absent-reason Extension für Datenschutz im digitalen Durchschlag"
    * insert treeSource(kbvMedicationRequest, subject, srcSubject)
    * insert treeTarget(bfarmMedicationRequest, subject, tgtSubject)
    * rule[+]
      * name = "medicationRequestsubjectExtension"
      * documentation = "Erstellt data-absent-reason Extension für Subject"
      * insert treeSource(kbvMedicationRequest, subject, srcSubject)
      * insert treeTarget(tgtSubject, extension, tgtSubjectExtension)
      * rule[+]
        * name = "medicationRequestsubjectExtensionContent"
        * documentation = "Setzt data-absent-reason auf 'not-permitted' um Patientendaten zu anonymisieren"
        * insert treeSource(kbvMedicationRequest, subject, srcSubject)
        * insert targetSetStringVariable(tgtSubjectExtension, url, http://hl7.org/fhir/StructureDefinition/data-absent-reason)
        * insert targetSetCodeVariable(tgtSubjectExtension, value, not-permitted)

  // authoredOn
  * rule[+]
    * name = "medicationRequestAuthoredOn"
    * insert treeSource(kbvMedicationRequest, authoredOn, srcAuthoredOnVar)
    * insert targetSetIdVariable(bfarmMedicationRequest, authoredOn, srcAuthoredOnVar)
    * documentation = "Übernimmt das Verschreibungsdatum unverändert vom KBV MedicationRequest"

  // dosageInstruction
  * rule[+]
    * name = "medicationRequestDosageInstruction"
    * insert treeSource(kbvMedicationRequest, dosageInstruction, srcDosageInstructionVar)
    * insert targetSetIdVariable(bfarmMedicationRequest, dosageInstruction, srcDosageInstructionVar)
    * documentation = "Kopiert die Dosierungsanweisungen vollständig für den digitalen Durchschlag"

  // dispenseRequest
  * rule[+]
    * name = "medicationRequestDispenseRequest"
    * insert treeSource(kbvMedicationRequest, dispenseRequest, srcDispenseRequestVar)
    * insert targetSetIdVariable(bfarmMedicationRequest, dispenseRequest, srcDispenseRequestVar)
    * documentation = "Übernimmt Abgabeanweisungen (Menge, Wiederholungen) aus der ursprünglichen Verschreibung"

  // reference to Medication
  * rule[+]
    * name = "medicationReference"
    * insert treeSource(kbvMedicationRequest, medication, medicationVar)
    * insert targetSetIdVariable(bfarmMedicationRequest, medication, medicationVar)
    * documentation = "Kopiert die Medikamentenreferenz - das referenzierte Medication wird separat gemappt"
