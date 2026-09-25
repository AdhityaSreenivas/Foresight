const fs = require('fs');

function testHtmlFile(filename) {
  console.log(`\n========================================`);
  console.log(`TESTING FILE: ${filename}`);
  console.log(`========================================`);
  const html = fs.readFileSync(filename, 'utf8');

  const requiredIds = [
    'psifDblClickRow',
    'iogpDblClickRow',
    'psifModal',
    'iogpModal',
    'psifModalCloseBtn',
    'psifModalOkBtn',
    'iogpModalCloseBtn',
    'iogpModalOkBtn',
    'psifModalIncidentSub',
    'psifModalClassificationText',
    'psifModalPrecursorText',
    'psifModalTriggersList',
    'iogpModalIncidentSub',
    'iogpModalPrimaryText',
    'iogpModalSecondaryText',
    'iogpModalComplianceText',
    'incidentSelect',
    'clickHintToast'
  ];

  let missing = 0;
  requiredIds.forEach(id => {
    if (!html.includes(`id="${id}"`)) {
      console.error(`FAIL: Missing element with id="${id}"`);
      missing++;
    }
  });
  if (missing === 0) {
    console.log(`PASS: All ${requiredIds.length} required DOM elements exist.`);
  }

  // Verify inline ondblclick attributes
  if (html.includes(`id="psifDblClickRow"`) && html.includes(`ondblclick="window.openPsifDetails(event)"`)) {
    console.log(`PASS: #psifDblClickRow has inline ondblclick="window.openPsifDetails(event)"`);
  } else {
    console.error(`FAIL: #psifDblClickRow missing inline ondblclick`);
  }

  if (html.includes(`id="iogpDblClickRow"`) && html.includes(`ondblclick="window.openIogpDetails(event)"`)) {
    console.log(`PASS: #iogpDblClickRow has inline ondblclick="window.openIogpDetails(event)"`);
  } else {
    console.error(`FAIL: #iogpDblClickRow missing inline ondblclick`);
  }

  // Verify CSS properties
  if (html.includes('cursor: pointer !important;')) {
    console.log(`PASS: CSS defines cursor: pointer !important on rows.`);
  } else {
    console.error(`FAIL: CSS missing cursor: pointer !important`);
  }

  if (html.includes('pointer-events: none !important;')) {
    console.log(`PASS: CSS defines pointer-events: none !important on child elements.`);
  } else {
    console.error(`FAIL: CSS missing pointer-events: none !important on children`);
  }

  // Verify JS handlers
  const checks = [
    'window.openPsifDetails = function',
    'window.openIogpDetails = function',
    'psifRow.addEventListener(\'dblclick\'',
    'iogpRow.addEventListener(\'dblclick\'',
    'psifRow.addEventListener(\'click\'',
    'iogpRow.addEventListener(\'click\'',
    'psifModalTriggersList',
    'iogpModalPrimaryText',
    'renderIncident',
    'INCIDENT_DATABASE'
  ];

  checks.forEach(chk => {
    if (html.includes(chk)) {
      console.log(`PASS: JS includes "${chk}"`);
    } else {
      console.error(`FAIL: JS missing "${chk}"`);
    }
  });
}

testHtmlFile('index.html');
testHtmlFile('incident-classification.html');
