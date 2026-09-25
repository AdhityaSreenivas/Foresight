const fs = require('fs');
const vm = require('vm');

// Create a DOM mock environment
class MockElement {
  constructor(id, tagName = 'div') {
    this.id = id;
    this.tagName = tagName;
    this._classes = new Set();
    this.classList = {
      add: (c) => this._classes.add(c),
      remove: (c) => this._classes.delete(c),
      contains: (c) => this._classes.has(c)
    };
    this.listeners = {};
    this.style = {};
    this.textContent = '';
    this.innerHTML = '';
    this.children = [];
    this.value = '';
    this.dataset = {};
  }
  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(f => f !== fn);
    }
  }
  dispatchEvent(event) {
    const list = this.listeners[event.type] || [];
    list.forEach(fn => fn(event));
  }
  click() {
    this.dispatchEvent({ type: 'click', preventDefault: () => {}, stopPropagation: () => {} });
  }
  appendChild(child) {
    this.children.push(child);
  }
  querySelector(sel) {
    return this.children.find(c => c.value === sel.replace(/.*value="([^"]+)".*/, '$1')) || new MockElement('mock-option');
  }
  getBoundingClientRect() {
    return { top: 100, left: 100, width: 800, height: 60, right: 900, bottom: 160 };
  }
}

const elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = new MockElement(id);
  return elements[id];
}

// Pre-create known elements
[
  'psifDblClickRow', 'iogpDblClickRow', 'psifModal', 'iogpModal',
  'psifModalCloseBtn', 'psifModalOkBtn', 'iogpModalCloseBtn', 'iogpModalOkBtn',
  'clickHintToast', 'psifModalIncidentSub', 'psifModalClassificationText',
  'psifModalPrecursorText', 'psifModalTriggersList', 'iogpModalIncidentSub',
  'iogpModalPrimaryText', 'iogpModalSecondaryText', 'iogpModalBarrierText',
  'iogpModalLsrText', 'iogpModalComplianceText',
  'incidentSelect', 'incidentIdLabel', 'incidentStatusTag', 'incidentDateLabel',
  'incidentTitle', 'incidentNarrative', 'metaFacility', 'metaUnit', 'metaActivity',
  'metaEngine', 'psifBox', 'psifBoxActiveStatus', 'psifBoxBadge', 'nonPsifBox',
  'nonPsifBoxActiveStatus', 'nonPsifBoxBadge', 'reasonsList', 'reasoningCountBadge',
  'iogpPrimaryName', 'iogpPrimaryCode', 'iogpPrimaryDesc', 'iogpBoxCodeBadge',
  'iogpSecondarySummary', 'psifRowSub', 'iogpRowSub', 'classificationGrid'
].forEach(getEl);

// Setup sandbox context
const sandbox = {
  document: {
    getElementById: (id) => getEl(id),
    createElement: (tag) => new MockElement('dynamic', tag),
  },
  window: {
    _listeners: {},
    addEventListener: function(event, fn) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(fn);
    },
    dispatchEvent: function(event) {
      const list = this._listeners[event.type] || [];
      list.forEach(fn => fn(event));
    },
    location: { search: '' },
    getComputedStyle: () => ({ gridTemplateAreas: '"psif reasoning" "nonpsif iogp"' }),
  },
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  MouseEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
  KeyboardEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
  URLSearchParams: class { constructor() { this.get = () => null; } }
};
sandbox.window.window = sandbox.window;
sandbox.window.document = sandbox.document;

// Extract script from index.html
const html = fs.readFileSync('index.html', 'utf8');
const scriptContent = html.match(/<script>([\s\S]*?)<\/script>/)[1];

vm.createContext(sandbox);
vm.runInContext(scriptContent, sandbox);

console.log('\n--- SIMULATING REAL-WORLD USER INTERACTIONS ---');

// Test 1: Single Click on PSIF Row
console.log('1. Testing single click on PSIF row...');
getEl('psifDblClickRow').click();
if (getEl('psifModal').classList.contains('open')) {
  console.error('FAIL: Modal opened on single click!');
} else {
  console.log('PASS: Modal remained CLOSED on single click.');
}

// Test 2: Double Click via Cadence (first click at t=0, second click at t=150ms)
console.log('2. Testing human double click (150ms delay) on PSIF row...');
let mockTime = 10000;
sandbox.Date = { now: () => mockTime };
getEl('psifDblClickRow').click(); // t = 10000
mockTime += 150;                  // t = 10150
getEl('psifDblClickRow').click(); // 2nd click 150ms later!

if (getEl('psifModal').classList.contains('open')) {
  console.log('PASS: PSIF Modal OPENED on double click!');
  console.log('      Modal Incident:', getEl('psifModalIncidentSub').textContent);
  console.log('      Modal Classification:', getEl('psifModalClassificationText').innerHTML);
} else {
  console.error('FAIL: PSIF Modal failed to open on double click!');
}

// Test 3: Close modal
sandbox.window.closeAllModals();
console.log('3. Closing modal... is open?', getEl('psifModal').classList.contains('open'));

// Test 4: Double Click via Native 'dblclick' event
console.log('4. Testing native dblclick event on PSIF row...');
getEl('psifDblClickRow').dispatchEvent(new sandbox.MouseEvent('dblclick', { bubbles: true }));
if (getEl('psifModal').classList.contains('open')) {
  console.log('PASS: PSIF Modal OPENED on native dblclick event!');
} else {
  console.error('FAIL: PSIF Modal failed to open on native dblclick event!');
}
sandbox.window.closeAllModals();

// Test 5: Dynamic Incident Switching & Verification
console.log('5. Switching incident to INC-2026-0843 (Rigging Failure During Crane Lift)...');
sandbox.renderIncident('INC-2026-0843');
mockTime += 2000;
getEl('psifDblClickRow').click();
mockTime += 150;
getEl('psifDblClickRow').click();
console.log('      PSIF Modal Incident after switch:', getEl('psifModalIncidentSub').textContent);
if (getEl('psifModalIncidentSub').textContent.includes('INC-2026-0843')) {
  console.log('PASS: PSIF Modal correctly bound to currently selected incident INC-2026-0843!');
} else {
  console.error('FAIL: Modal has wrong incident data!');
}
sandbox.window.closeAllModals();

// Test 6: Single Click on IOGP Row
console.log('6. Testing single click on IOGP row...');
mockTime += 2000;
getEl('iogpDblClickRow').click();
if (getEl('iogpModal').classList.contains('open')) {
  console.error('FAIL: IOGP Modal opened on single click!');
} else {
  console.log('PASS: IOGP Modal remained CLOSED on single click.');
}

// Test 7: Double Click on IOGP Row
console.log('7. Testing double click on IOGP row...');
mockTime += 150;
getEl('iogpDblClickRow').click();
if (getEl('iogpModal').classList.contains('open')) {
  console.log('PASS: IOGP Modal OPENED on double click!');
  console.log('      IOGP Modal Incident:', getEl('iogpModalIncidentSub').textContent);
  console.log('      IOGP Primary Barrier:', getEl('iogpModalPrimaryText').innerHTML);
} else {
  console.error('FAIL: IOGP Modal failed to open on double click!');
}
sandbox.window.closeAllModals();

// Test 8: Left, Center, and Right edge double-click tests
console.log('\n--- TESTING LEFT, CENTER, AND RIGHT BOUNDARIES ---');
const rect = getEl('psifDblClickRow').getBoundingClientRect();

// Left edge
getEl('psifDblClickRow').dispatchEvent(new sandbox.MouseEvent('dblclick', { bubbles: true, clientX: rect.left + 5 }));
console.log('Left edge double-click opened modal?', getEl('psifModal').classList.contains('open'));
sandbox.window.closeAllModals();

// Center
getEl('psifDblClickRow').dispatchEvent(new sandbox.MouseEvent('dblclick', { bubbles: true, clientX: rect.left + rect.width / 2 }));
console.log('Center double-click opened modal?', getEl('psifModal').classList.contains('open'));
sandbox.window.closeAllModals();

// Right edge
getEl('psifDblClickRow').dispatchEvent(new sandbox.MouseEvent('dblclick', { bubbles: true, clientX: rect.right - 5 }));
console.log('Right edge double-click opened modal?', getEl('psifModal').classList.contains('open'));
sandbox.window.closeAllModals();

// Test 9: Run Built-In runLayoutTests suite
console.log('\n--- EXECUTING IN-BROWSER window.runLayoutTests() SUITE ---');
mockTime += 2000;
const suiteResults = sandbox.window.runLayoutTests();
suiteResults.forEach(r => {
  console.log(`[Test ${r.test}] ${r.name}: ${r.passed ? 'PASSED' : 'FAILED'}`);
});
