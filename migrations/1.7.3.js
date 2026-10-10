const IDENTIFICATION_SKILLS = {
  aberration: ["occultism"],
  animal: ["nature"],
  astral: ["occultism"],
  beast: ["arcana", "nature"],
  celestial: ["religion"],
  construct: ["arcana", "crafting"],
  dragon: ["arcana"],
  dream: ["occultism"],
  elemental: ["arcana", "nature"],
  ethereal: ["occultism"],
  fey: ["nature"],
  fiend: ["religion"],
  fungus: ["nature"],
  humanoid: ["society"],
  monitor: ["religion"],
  ooze: ["occultism"],
  plant: ["nature"],
  shade: ["religion"],
  spirit: ["occultism"],
  time: ["occultism"],
  undead: ["religion"],
}

const LEADING_LINK = /^\[([^\]]+)\]\(([^)]+)\)(.*)$/s
const ACUITY = /^\s*\(\[([^\]]+)\]\(([^)]+)\)\)(.*)$/s
const PLAIN_ACUITY = /^(.*?)\s+\(\[([^\]]+)\]\(([^)]+)\)\)(.*)$/s
const QUANTITY = /^(.*?)\s+\((\d+)\)$/s
const ABILITY_TRIGGER = /\*\*Trigger\*\*\s*/i
const ABILITY_EFFECT = /\*\*Effect\*\*\s*/i
const ABILITY_METADATA = /\*\*(?:Frequency|Requirements|Trigger|Effect)\*\*\s*/i
const PARAGRAPH_BREAK = /\n\s*\n/

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function trimMetadataSeparator(value) {
  return String(value || "").trim().replace(/^;+|;+$/g, "").trim()
}

function joinAbilityDescription(before, after) {
  const leading = trimMetadataSeparator(before)
  const trailing = trimMetadataSeparator(after)
  if (leading && trailing) return `${leading}; ${trailing}`
  return leading || trailing
}

function abilityEditorFields(value) {
  let description = String(value || "").trim()
  const result = {}

  const effect = ABILITY_EFFECT.exec(description)
  if (effect) {
    result.effect = trimMetadataSeparator(description.slice(effect.index + effect[0].length))
    description = trimMetadataSeparator(description.slice(0, effect.index))
  }

  const trigger = ABILITY_TRIGGER.exec(description)
  if (trigger) {
    const valueStart = trigger.index + trigger[0].length
    const tail = description.slice(valueStart)
    const nextLabel = ABILITY_METADATA.exec(tail)
    const paragraph = PARAGRAPH_BREAK.exec(tail)
    const candidates = [nextLabel, paragraph]
      .filter(Boolean)
      .map((match) => valueStart + match.index)
    const valueEnd = candidates.length ? Math.min(...candidates) : description.length
    result.trigger = trimMetadataSeparator(description.slice(valueStart, valueEnd))
    const before = description.slice(0, trigger.index)
    let after = description.slice(valueEnd)
    result.triggerBeforeDescription = !trimMetadataSeparator(before)
    if (paragraph && valueStart + paragraph.index === valueEnd) {
      result.triggerParagraphBreak = true
      after = description.slice(valueEnd + paragraph[0].length)
    }
    description = joinAbilityDescription(before, after)
  }

  result.description = description
  return result
}

function splitEntries(value) {
  const result = []
  let start = 0
  let squareDepth = 0
  let roundDepth = 0
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index]
    if (char === "[") squareDepth += 1
    else if (char === "]" && squareDepth) squareDepth -= 1
    else if (char === "(") roundDepth += 1
    else if (char === ")" && roundDepth) roundDepth -= 1
    else if (char === "," && squareDepth === 0 && roundDepth === 0) {
      const entry = value.slice(start, index).trim()
      if (entry) result.push(entry)
      start = index + 1
    }
  }
  const entry = value.slice(start).trim()
  if (entry) result.push(entry)
  return result
}

function itemEntries(value) {
  return splitEntries(value).map((text) => {
    const linked = LEADING_LINK.exec(text)
    if (linked) {
      const entry = { name: linked[1], reference: linked[2] }
      let suffix = linked[3].trim()
      const quantity = /^(\d+)$/s.exec(suffix.replace(/^\(|\)$/g, ""))
      if (quantity) entry.quantity = Number(quantity[1])
      else if (suffix) entry.details = suffix
      return entry
    }
    const quantity = QUANTITY.exec(text)
    if (quantity) return { name: quantity[1].trim(), quantity: Number(quantity[2]) }
    return { name: text }
  })
}

function senseEntries(value) {
  const parts = splitEntries(value)
  if (parts.join(", ") !== value.trim()) return [{ customText: value.trim() }]
  return parts.map((text) => {
    const linked = LEADING_LINK.exec(text)
    if (linked) {
      const entry = { name: linked[1], reference: linked[2] }
      let suffix = linked[3]
      const acuity = ACUITY.exec(suffix)
      if (acuity) {
        entry.acuity = acuity[1]
        entry.acuityReference = acuity[2]
        suffix = acuity[3]
      }
      if (suffix.trim()) entry.details = suffix.trim()
      return entry
    }
    const acuity = PLAIN_ACUITY.exec(text)
    if (acuity && !acuity[1].includes("[")) {
      const entry = {
        name: acuity[1].trim(),
        acuity: acuity[2],
        acuityReference: acuity[3],
      }
      if (acuity[4].trim()) entry.details = acuity[4].trim()
      return entry
    }
    if (text.includes("[") || text.includes("](")) return { customText: text }
    return { name: text }
  })
}

function referenceEntry(value) {
  const linked = LEADING_LINK.exec(value)
  if (!linked) {
    if (value.includes("[") || value.includes("](")) return { customText: value }
    return { name: value }
  }
  const entry = { name: linked[1], reference: linked[2] }
  if (linked[3].trim()) entry.details = linked[3].trim()
  return entry
}

function migrate(entity, migration) {
  if (entity.kind !== "Creature" || !entity.data) return null
  const data = entity.data
  let changed = false

  const recall = data.recallKnowledge
  if (recall && recall.dc && (!Array.isArray(recall.entries) || !recall.entries.length)) {
    const subjects = Array.isArray(recall.subjects)
      ? recall.subjects
      : recall.subject
        ? [recall.subject]
        : []
    if (subjects.length) {
      recall.entries = subjects.map((subject) => ({
        subject,
        skills: clone(IDENTIFICATION_SKILLS[subject] || recall.skills || []),
      }))
      changed = true
    }
  }

  if (!data.skillsEditor && (data.skills || data.loreSkills)) {
    data.skillsEditor = {
      skills: clone(data.skills || {}),
      loreSkills: clone(data.loreSkills || []),
    }
    changed = true
  }
  if (!data.senseEntries && typeof data.senses === "string" && data.senses.trim()) {
    data.senseEntries = senseEntries(data.senses)
    changed = true
  }
  if (!data.itemEntries && typeof data.items === "string" && data.items.trim()) {
    data.itemEntries = itemEntries(data.items)
    changed = true
  }
  if (!data.immunityEditor && Array.isArray(data.immunities) && data.immunities.length) {
    data.immunityEditor = { entries: data.immunities.map((value) => referenceEntry(String(value))) }
    changed = true
  }
  if (!data.ritualcasting && data.rituals && typeof data.rituals === "object") {
    data.ritualcasting = [clone(data.rituals)]
    changed = true
  }
  if (!data.weaknessEntries && data.weaknesses && Object.keys(data.weaknesses).length) {
    data.weaknessEntries = Object.entries(data.weaknesses).map(([type, value]) => ({ type, value: clone(value) }))
    changed = true
  }
  if (!data.resistanceEntries && data.resistances && Object.keys(data.resistances).length) {
    data.resistanceEntries = Object.entries(data.resistances).map(([type, value]) => ({ type, value: clone(value) }))
    changed = true
  }
  const abilities = data.abilities
  if (abilities && typeof abilities === "object") {
    for (const entries of Object.values(abilities)) {
      if (!Array.isArray(entries)) continue
      for (const ability of entries) {
        if (!ability || typeof ability !== "object" || "description" in ability) continue
        Object.assign(ability, abilityEditorFields(ability.text))
        changed = true
      }
    }
  }

  return changed ? entity : null
}
