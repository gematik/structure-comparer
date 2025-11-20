RuleSet: sd_structure(url, mode, alias)
* structure[+]
  * url = "{url}"
  * mode = #{mode}
  * alias = "{alias}"

RuleSet: sd_input(name, mode)
* input[+]
  * name = "{name}"
  * type = "{name}"
  * mode = #{mode}

RuleSet: targetBase(context, to)
* target[+]
  * context = "{context}"
  * contextType = #variable
  * element = "{to}"
  * transform = #copy


RuleSet: targetSetIdVariable(context, to, id)
* insert targetBase({context}, {to})
* target[=].parameter.valueId = "{id}"

RuleSet: targetSetStringVariable(context, to, string)
* insert targetBase({context}, {to})
* target[=].parameter.valueString = "{string}"

RuleSet: targetSetCodeVariable(context, to, code)
* target[+]
  * context = "{context}"
  * contextType = #variable
  * element = "{to}"
  * transform = #cast
  * parameter[+].valueString = "{code}"
  * parameter[+].valueString = "code"

RuleSet: targetSetIdentifierVariable(context, to, system, value)
* target[+]
  * context = "{context}"
  * contextType = #variable
  * element = "{to}"
  * transform = #id
  * parameter[+].valueString = "{system}"
  * parameter[+].valueString = "{value}"

RuleSet: createType(context, to, variable, type)
* target[+]
  * context = "{context}"
  * contextType = #variable
  * element = "{to}"
  * transform = #create
  * variable = "{variable}"
  * parameter[+].valueString = "{type}"

RuleSet: treeSource(context, element, variable)
* source[+]
  * context = "{context}"
  * element = "{element}"
  * variable = "{variable}"

RuleSet: treeTarget(context, element, variable)
* target[+]
  * contextType = #variable
  * context = "{context}"
  * element = "{element}"
  * variable = "{variable}"

RuleSet: dependent(name, src, tgt)
* dependent[+]
  * name = "{name}"
  * variable[+] = "{src}"
  * variable[+] = "{tgt}"
        