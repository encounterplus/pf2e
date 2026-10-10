const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const stylesheet = fs.readFileSync(path.join(root, 'styles', 'default.css'), 'utf8');
const pages = fs.readFileSync(path.join(root, 'pages.json'), 'utf8');

const palette = {
  page: '#181716',
  surface: '#22201f',
  raised: '#2b2927',
  border: '#4a4642',
  text: '#f1ede6',
  muted: '#b8b0a7',
  crimson: '#d17a68',
  gold: '#d2b66f',
  link: '#68b5d2',
};

test('defines the approved shared dark palette', () => {
  for (const [name, value] of Object.entries(palette)) {
    assert.match(stylesheet, new RegExp(`--pf-dark-${name}:\\s*${value};`));
  }
});

test('uses the palette for the XP planner and Operations Center', () => {
  assert.match(stylesheet, /--xp-paper:\s*#181716;/);
  assert.match(stylesheet, /--xp-panel:\s*#22201f;/);
  assert.match(stylesheet, /--xp-accent:\s*#d17a68;/);
  assert.match(stylesheet, /--ops-paper:\s*#181716;/);
  assert.match(stylesheet, /--ops-panel:\s*#22201f;/);
  assert.match(stylesheet, /--ops-green:\s*#d2b66f;/);
  assert.match(stylesheet, /--ops-link:\s*#68b5d2;/);
  assert.match(pages, /--ops-paper:\s*#181716;/);
});

test('preserves informational rarity and trait colors', () => {
  assert.match(stylesheet, /--tag-default-color:\s*#5E0000;/);
  assert.match(stylesheet, /--tag-blue-color:\s*#002664;/);
  assert.match(stylesheet, /--tag-purple-color:\s*#54166E;/);
  assert.match(stylesheet, /--tag-green-color:\s*#3a7a58;/);
  assert.match(stylesheet, /--tag-orange-color:\s*#98513D;/);
  assert.match(stylesheet, /\.trait-rarity-uncommon\s*\{[\s\S]*?var\(--tag-orange-color\)/);
  assert.match(stylesheet, /\.trait-rarity-rare\s*\{[\s\S]*?var\(--tag-blue-color\)/);
  assert.match(stylesheet, /\.trait-rarity-unique\s*\{[\s\S]*?var\(--tag-purple-color\)/);
  assert.match(stylesheet, /\.trait-size\s*\{[\s\S]*?var\(--tag-green-color\)/);
});

test('wraps trait and footer tags instead of shrinking compact sheets', () => {
  assert.match(stylesheet, /\.traits\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-wrap:\s*wrap;/);
  assert.match(stylesheet, /\.tags\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-wrap:\s*wrap;/);
});

test('library footer tags keep readable colors in light and dark modes', () => {
  assert.match(stylesheet, /--footer-tag-background:\s*white;/);
  assert.match(stylesheet, /--pf-dark-tag:\s*#302d2b;/);
  assert.match(stylesheet, /--pf-dark-tag-text:\s*#ddd6cc;/);
  assert.match(stylesheet, /--footer-tag-background:\s*var\(--pf-dark-tag\);/);
  assert.match(stylesheet, /--footer-tag-text:\s*var\(--pf-dark-tag-text\);/);
  assert.match(stylesheet, /background-color:\s*var\(--footer-tag-background\);/);
  assert.match(stylesheet, /color:\s*var\(--footer-tag-text\);/);
});

test('HTML views share one versioned system stylesheet cache key', () => {
  const base = fs.readFileSync(path.join(root, 'views/partials/base.html'), 'utf8');
  const match = base.match(/styles\/default\.css\?v=([0-9.]+)/);
  assert.ok(match, 'base view must use a versioned system stylesheet');
  const expectedStylesheet = match[0];
  const directViews = [
    'views/class.html',
    'views/deity.html',
    'views/default.html',
    'views/ancestry.html',
  ];

  for (const file of directViews) {
    const template = fs.readFileSync(path.join(root, file), 'utf8');
    assert.ok(template.includes(expectedStylesheet), `${file} must load ${expectedStylesheet}`);
  }

  const standaloneBridge = fs.readFileSync(path.join(root, 'assets/css/custom.css'), 'utf8');
  assert.ok(
    standaloneBridge.includes(`../../${expectedStylesheet}`),
    'standalone pages must load the versioned system stylesheet'
  );
});
