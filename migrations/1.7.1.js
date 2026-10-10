const DAMAGE_FORMULA = /(^|[^A-Za-z0-9])((?:\d+)?d\d+(?:\s*[+-]\s*\d+)?)/gi
const DAMAGE_CONNECTOR = /(?:\s*(;|,)|\s+\b(plus|and)\b)\s*$/i

function splitDamageConnector(text) {
  const match = DAMAGE_CONNECTOR.exec(text)
  if (!match) return { text: text.trim(), connector: " plus " }

  const token = String(match[1] || match[2] || "").toLowerCase()
  const connectors = {
    ";": "; ",
    ",": ", ",
    plus: " plus ",
    and: " and ",
  }
  return {
    text: text.slice(0, match.index).trim(),
    connector: connectors[token],
  }
}

function parseDamageParts(value) {
  if (typeof value !== "string" || !value.trim()) return []

  const text = value.trim()
  const matches = []
  DAMAGE_FORMULA.lastIndex = 0
  let match
  while ((match = DAMAGE_FORMULA.exec(text)) !== null) {
    const leadingLength = match[1].length
    matches.push({
      start: match.index + leadingLength,
      end: DAMAGE_FORMULA.lastIndex,
      formula: match[2].replace(/\s+/g, ""),
    })
  }
  if (!matches.length) return [{ details: text }]

  const parts = []
  let pending = splitDamageConnector(text.slice(0, matches[0].start))
  if (pending.text) parts.push({ details: pending.text })

  for (let index = 0; index < matches.length; index += 1) {
    const current = matches[index]
    const end = index + 1 < matches.length ? matches[index + 1].start : text.length
    const following = splitDamageConnector(text.slice(current.end, end))
    const part = { formula: current.formula, details: following.text }
    if (parts.length) part.connector = pending.connector
    parts.push(part)
    pending = following
  }
  return parts
}

function migrate(entity, migration) {
  if (entity.kind !== "Creature") return null

  const attacks = entity.data && entity.data.attacks
  if (!Array.isArray(attacks)) return null

  let changed = false
  for (const attack of attacks) {
    if (!attack || Array.isArray(attack.damageParts)) continue
    const parts = parseDamageParts(attack.damage)
    if (!parts.length) continue
    attack.damageParts = parts
    changed = true
  }

  if (!changed) return null
  return entity
}
