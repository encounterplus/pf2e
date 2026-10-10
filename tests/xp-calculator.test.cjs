const test = require("node:test");
const assert = require("node:assert/strict");
const calculator = require("../scripts/xp-calculator.js");

function encounter(overrides = {}) {
  return calculator.calculateEncounter({
    partyLevel: 5,
    partySize: 4,
    additionalXp: 0,
    entries: [],
    ...overrides
  });
}

test("uses the GM Core creature and complex hazard XP table", () => {
  assert.deepEqual(
    [-4, -3, -2, -1, 0, 1, 2, 3, 4].map((delta) => calculator.xpFor("creature", delta)),
    [10, 15, 20, 30, 40, 60, 80, 120, 160]
  );
  assert.equal(calculator.xpFor("complex-hazard", 0), 40);
});

test("uses the GM Core simple hazard XP table", () => {
  assert.deepEqual(
    [-4, -3, -2, -1, 0, 1, 2, 3, 4].map((delta) => calculator.xpFor("simple-hazard", delta)),
    [2, 3, 4, 6, 8, 12, 16, 24, 32]
  );
});

test("two creatures at party level make a moderate encounter", () => {
  const result = encounter({
    entries: [{ kind: "creature", level: 5, adjustment: 0, quantity: 2 }]
  });
  assert.equal(result.encounterXp, 80);
  assert.equal(result.threat, "moderate");
  assert.equal(result.awardedXp, 80);
});

test("one party-level-plus-two creature is worth 80 XP", () => {
  const result = encounter({
    entries: [{ kind: "creature", level: 7, adjustment: 0, quantity: 1 }]
  });
  assert.equal(result.encounterXp, 80);
  assert.equal(result.threat, "moderate");
});

test("adjusts every threat budget for a five-PC party", () => {
  assert.deepEqual(calculator.adjustedBudgets(5), {
    trivial: 50,
    low: 80,
    moderate: 100,
    severe: 150,
    extreme: 200
  });
});

test("adjusts every threat budget for a three-PC party", () => {
  assert.deepEqual(calculator.adjustedBudgets(3), {
    trivial: 30,
    low: 40,
    moderate: 60,
    severe: 90,
    extreme: 120
  });
});

test("weak and elite adjustments change effective level before XP lookup", () => {
  const result = encounter({
    entries: [
      { kind: "creature", level: 5, adjustment: -1, quantity: 1 },
      { kind: "creature", level: 5, adjustment: 1, quantity: 1 }
    ]
  });
  assert.equal(result.entries[0].eachXp, 30);
  assert.equal(result.entries[1].eachXp, 60);
  assert.equal(result.encounterXp, 90);
});

test("manual override supports unusual entries without silently clamping", () => {
  const automatic = encounter({
    entries: [{ kind: "creature", level: 10, adjustment: 0, quantity: 1 }]
  });
  assert.equal(automatic.entries[0].eachXp, null);
  assert.equal(automatic.entries[0].outOfRange, true);
  assert.equal(automatic.encounterXp, 0);
  assert.equal(automatic.warnings, 1);

  const overridden = encounter({
    entries: [{ kind: "creature", level: 10, adjustment: 0, quantity: 2, overrideXp: 200 }]
  });
  assert.equal(overridden.entries[0].outOfRange, false);
  assert.equal(overridden.encounterXp, 400);
});

test("additional awards affect awarded XP but not encounter threat", () => {
  const result = encounter({
    additionalXp: 30,
    entries: [{ kind: "simple-hazard", level: 5, adjustment: 0, quantity: 1 }]
  });
  assert.equal(result.encounterXp, 8);
  assert.equal(result.awardedXp, 38);
  assert.equal(result.threat, "trivial");
});

test("an invalid manual override is flagged", () => {
  const result = encounter({
    entries: [{ kind: "creature", level: 5, adjustment: 0, quantity: 1, overrideXp: -1 }]
  });
  assert.equal(result.entries[0].invalidOverride, true);
  assert.equal(result.warnings, 1);
});

test("native award handoff uses the full per-PC award", () => {
  const result = encounter({
    additionalXp: 30,
    entries: [{ kind: "creature", level: 5, adjustment: 0, quantity: 2 }]
  });
  assert.equal(calculator.nativeAwardValue(result), "110");
});
