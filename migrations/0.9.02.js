// Prepared for the next release. Keep in sync with tools/spell_load_data.py.
const SPELL_TURN_DURATIONS = {
  "until the start of your next turn": "sourceStartNextTurn",
  "until the beginning of your next turn": "sourceStartNextTurn",
  "until the end of your next turn": "sourceEndNextTurn",
  "until the start of the target's next turn": "targetStartNextTurn",
  "until the end of the target's next turn": "targetEndNextTurn",
  "until the end of your target's next turn": "targetEndNextTurn",
}
const SPELL_TIMED_DURATION = /^(?:(?:sustain(?:ed)?\s+(?:for\s+)?)?up to\s+)?(\d+)\s+(round|minute|hour|day|week)s?(?:\s*\(see text\)|\s+or until (?:expended|used|discharged))?$/i

function migrate(entity, migration) {
  if (entity.kind !== "Spell" || !entity.data) return null
  const data = entity.data
  if (typeof data.duration !== "string") {
    if (data.duration == null && !data.durationType && !data.durationUnit) {
      data.durationUnit = "round"
      return entity
    }
    return null
  }
  if (data.durationType || data.durationUnit) return null
  const text = data.duration
  const manual = data.durationType === ""
  if (data.durationText === undefined) data.durationText = text
  delete data.duration
  delete data.durationType
  delete data.durationUnit

  const normalized = text.toLowerCase().trim().replace(/\s+/g, " ")
  const turnType = manual ? null : SPELL_TURN_DURATIONS[normalized]
  if (turnType) {
    data.durationType = turnType
    data.duration = 1
    data.durationUnit = "round"
  } else {
    const timed = manual ? null : SPELL_TIMED_DURATION.exec(normalized)
    if (timed && Number(timed[1]) > 0) {
      data.durationType = "time"
      data.duration = Number(timed[1]) * (timed[2] === "week" ? 7 : 1)
      data.durationUnit = timed[2] === "week" ? "day" : timed[2]
    } else {
      // A unit-only native descriptor creates a reminder without expiry.
      data.durationUnit = "round"
    }
  }
  return entity
}
