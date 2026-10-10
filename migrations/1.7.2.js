function damagePartWithHumanTitle(part) {
  if (!part || typeof part !== "object" || part.name) return false

  if (part.formula) {
    part.name = part.formula
    delete part.formula
    return true
  }

  if (typeof part.details === "string" && part.details.trim()) {
    const text = part.details.trim()
    const separator = text.indexOf(" ")
    part.name = separator < 0 ? text : text.slice(0, separator)
    part.details = separator < 0 ? "" : text.slice(separator + 1).trim()
    return true
  }

  return false
}

function migrate(entity, migration) {
  if (entity.kind !== "Creature") return null

  const attacks = entity.data && entity.data.attacks
  if (!Array.isArray(attacks)) return null

  let changed = false
  for (const attack of attacks) {
    if (!attack || !Array.isArray(attack.damageParts)) continue
    for (const part of attack.damageParts) {
      if (damagePartWithHumanTitle(part)) changed = true
    }
  }

  return changed ? entity : null
}
