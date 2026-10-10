const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function readJson5(file) {
  const source = fs.readFileSync(file, 'utf8');
  return JSON.parse(source.replace(/,\s*([}\]])/g, '$1'));
}

function loadMigration(version) {
  const source = fs.readFileSync(
    path.join(root, 'migrations', `${version}.js`),
    'utf8'
  );
  const context = {};
  vm.runInNewContext(`${source}\nthis.__migrate = migrate`, context);
  return context.__migrate;
}

test('the creature editor exposes repeatable, optional damage components', () => {
  const attackForm = readJson5(path.join(root, 'forms', 'partials', 'attack.json'));
  const damageList = attackForm.sections.find(
    (section) => section.attribute === 'damageParts'
  );

  assert.ok(damageList, 'attack editor must expose damage components');
  assert.equal(damageList.type, 'list');
  assert.equal(damageList.form.partial, 'damage-part');

  const componentForm = readJson5(
    path.join(root, 'forms', 'partials', 'damage-part.json')
  );
  const fields = componentForm.sections.flatMap((section) => section.fields || []);
  const dice = fields.find((field) => field.attribute === 'name');
  const details = fields.find((field) => field.attribute === 'details');

  assert.equal(dice.type, 'text');
  assert.equal(details.type, 'text');
  assert.equal(dice.placeholder, 'Common.Optional');
  assert.equal(details.placeholder, 'Common.Optional');
  assert.equal(damageList.custom.itemDetail, '{{details}}');
  assert.match(dice.title, /Formula/);
  assert.match(details.title, /Description/);

  const english = readJson5(path.join(root, 'lang', 'en.json'));
  assert.equal(english[dice.title], 'Damage Die/s');
  assert.equal(english[details.title], 'Damage Type or Effect');
});

test('the shared attack template emits an explicitly typed damage roll', () => {
  const template = fs.readFileSync(
    path.join(root, 'views', 'partials', 'attack.md'),
    'utf8'
  );

  assert.match(template, /{% for damage in ability\.damageParts %}/);
  assert.match(template, /damage\.name\|roll: ability\.name, 'damage'/);
  assert.match(template, /damage\.formula\|roll: ability\.name, 'damage'/);
  assert.match(template, /damage\.details\|prefix: ' '/);
  assert.match(template, /{% else %}\{\{ability\.damage\}\}{% endif %}/);
  assert.doesNotMatch(template, /{%\s*elsif\b/);
});

test('the migration separates formulas from optional damage descriptions', () => {
  const migrateLegacyDamage = loadMigration('1.7.1');
  const migrateHumanTitles = loadMigration('1.7.2');
  const creature = {
    kind: 'Creature',
    data: {
      attacks: [
        { name: 'Mandibles', damage: '1d4+1 piercing' },
        { name: 'Force Bolt', damage: '3d6' },
        { name: 'Flaming Jaws', damage: '2d8+12 piercing plus 2d6 fire' },
        { name: 'Static Harm', damage: '1 persistent bleed' },
      ],
    },
  };

  migrateLegacyDamage(creature, {});
  const result = migrateHumanTitles(creature, {});
  const attacks = JSON.parse(JSON.stringify(result.data.attacks));

  assert.deepEqual(attacks[0].damageParts, [
    { name: '1d4+1', details: 'piercing' },
  ]);
  assert.deepEqual(attacks[1].damageParts, [
    { name: '3d6', details: '' },
  ]);
  assert.deepEqual(attacks[2].damageParts, [
    { name: '2d8+12', details: 'piercing' },
    { name: '2d6', details: 'fire', connector: ' plus ' },
  ]);
  assert.deepEqual(attacks[3].damageParts, [
    { name: '1', details: 'persistent bleed' },
  ]);

  assert.equal(migrateHumanTitles(creature, {}), null, 'migration must be idempotent');
});

test('legacy compendium damage remains available for migration and fallback', () => {
  const packRoot = path.join(root, 'compendium', 'packs');
  let checked = 0;

  for (const source of fs.readdirSync(packRoot)) {
    const file = path.join(packRoot, source, 'creatures.json');
    if (!fs.existsSync(file)) continue;

    for (const creature of JSON.parse(fs.readFileSync(file, 'utf8'))) {
      for (const attack of creature.data?.attacks || []) {
        if (!attack.damage) continue;
        assert.equal(typeof attack.damage, 'string');
        assert.doesNotMatch(attack.damage, /\]\((?:\/)?roll\b/);
        checked += 1;
      }
    }
  }

  assert.ok(checked > 3000, `expected broad creature coverage, checked ${checked}`);
});
