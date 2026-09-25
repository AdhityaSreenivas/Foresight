const fs = require('fs');

function verifyModalArchitecture(filename) {
  console.log(`\n======================================================`);
  console.log(`VERIFYING MODAL INFORMATION ARCHITECTURE: ${filename}`);
  console.log(`======================================================`);
  const html = fs.readFileSync(filename, 'utf8');

  // ==========================================
  // 1. PSIF MODAL: EXACTLY 5 BOXES (SIDE-BY-SIDE)
  // ==========================================
  const psifBoxIds = ['psifBox1', 'psifBox2', 'psifBox3', 'psifBox4', 'psifBox5'];
  let missingPsifBoxes = 0;
  psifBoxIds.forEach(id => {
    if (!html.includes(`id="${id}"`)) {
      console.error(`FAIL: Missing PSIF box: id="${id}"`);
      missingPsifBoxes++;
    }
  });

  if (missingPsifBoxes === 0) {
    console.log(`PASS: All 5 PSIF distinct information boxes found (psifBox1 - psifBox5).`);
  }

  // Count occurrences of id="psifBox in file
  const psifMatches = html.match(/id="psifBox\d"/g) || [];
  if (psifMatches.length === 5) {
    console.log(`PASS: Count of PSIF boxes is EXACTLY 5 (found ${psifMatches.length}).`);
  } else {
    console.error(`FAIL: Count of PSIF boxes is NOT 5 (found ${psifMatches.length}).`);
  }

  // Check PSIF 2-column side-by-side grid
  if (html.includes('.psif-modal-grid') && html.includes('grid-template-columns: repeat(2, 1fr)')) {
    console.log(`PASS: PSIF modal has responsive side-by-side grid layout (.psif-modal-grid).`);
  } else {
    console.error(`FAIL: PSIF modal missing side-by-side grid definition.`);
  }

  // Check PSIF Box Titles
  const requiredPsifTitles = [
    ['PSIF CLASSIFICATION'],
    ['PRECURSOR IDENTIFICATION', 'PRECURSOR CONDITION'],
    ['ENERGY / HAZARD MECHANISM', 'HAZARDOUS ENERGY & RELEASE MECHANICS'],
    ['CONTROL / BARRIER FAILURE', 'EVALUATED PRECURSOR TRIGGERS & RULES'],
    ['POTENTIAL CONSEQUENCE / SIF ASSESSMENT', 'POTENTIAL SEVERITY & DEKRA SIF FRAMEWORK ASSESSMENT']
  ];

  requiredPsifTitles.forEach((variants, idx) => {
    const matched = variants.find(t => html.includes(`<h3>${t}</h3>`));
    if (matched) {
      console.log(`PASS: PSIF Box ${idx + 1} Title correct: "${matched}"`);
    } else {
      console.error(`FAIL: PSIF Box ${idx + 1} missing title from: ${JSON.stringify(variants)}`);
    }
  });

  // Check Box 1 Distinction: Classification Result vs Rules-Based Assessment Basis
  if (html.includes('Classification Result') && html.includes('Rules-Based Assessment Basis')) {
    console.log(`PASS: PSIF Box 1 clearly distinguishes between Classification Result and Rules-Based Assessment Basis.`);
  } else {
    console.error(`FAIL: PSIF Box 1 does not clearly distinguish between Classification Result and Rules-Based Assessment Basis.`);
  }

  // ==========================================
  // 2. IOGP MODAL: EXACTLY 5 BOXES
  // ==========================================
  const iogpBoxIds = ['iogpBox1', 'iogpBox2', 'iogpBox3', 'iogpBox4', 'iogpBox5'];
  let missingIogpBoxes = 0;
  iogpBoxIds.forEach(id => {
    if (!html.includes(`id="${id}"`)) {
      console.error(`FAIL: Missing IOGP box: id="${id}"`);
      missingIogpBoxes++;
    }
  });

  if (missingIogpBoxes === 0) {
    console.log(`PASS: All 5 IOGP distinct information boxes found (iogpBox1 - iogpBox5).`);
  }

  // Count occurrences of id="iogpBox in file
  const iogpMatches = html.match(/id="iogpBox\d"/g) || [];
  if (iogpMatches.length === 5) {
    console.log(`PASS: Count of IOGP boxes is EXACTLY 5 (found ${iogpMatches.length}).`);
  } else {
    console.error(`FAIL: Count of IOGP boxes is NOT 5 (found ${iogpMatches.length}).`);
  }

  // Check IOGP 2-column side-by-side grid
  if (html.includes('.iogp-modal-grid') && html.includes('grid-template-columns: repeat(2, 1fr)')) {
    console.log(`PASS: IOGP modal has responsive side-by-side grid layout (.iogp-modal-grid).`);
  } else {
    console.error(`FAIL: IOGP modal missing side-by-side grid definition.`);
  }

  // Check IOGP Box Titles
  const requiredIogpTitles = [
    ['PRIMARY IOGP CATEGORY'],
    ['SECONDARY IOGP CATEGORY'],
    ['BARRIER ALIGNMENT'],
    ['LIFE-SAVING RULE ALIGNMENT'],
    ['IOGP REPORT 459 REFERENCE', 'REPORT 459 / IOGP REFERENCE']
  ];

  requiredIogpTitles.forEach((variants, idx) => {
    const matched = variants.find(t => html.includes(`<h3>${t}</h3>`));
    if (matched) {
      console.log(`PASS: IOGP Box ${idx + 1} Title correct: "${matched}"`);
    } else {
      console.error(`FAIL: IOGP Box ${idx + 1} missing title from: ${JSON.stringify(variants)}`);
    }
  });

  // Verify Report 459 is inside Box 5 (iogpBox5)
  const box5Match = html.match(/id="iogpBox5"[\s\S]*?<\/div>\s*<\/div>/);
  if (box5Match && (box5Match[0].includes('REPORT 459') || box5Match[0].includes('IOGP REPORT 459 REFERENCE')) && box5Match[0].includes('iogpModalComplianceText')) {
    console.log(`PASS: Report 459 is contained inside Box 5 (iogpBox5) with iogpModalComplianceText.`);
  } else {
    console.error(`FAIL: Report 459 is not properly contained inside Box 5.`);
  }

  // Verify calibrated disclaimer language in Box 5
  if (html.includes('Reference mapping only — not a compliance certification.')) {
    console.log(`PASS: Box 5 uses calibrated disclaimer: "Reference mapping only — not a compliance certification."`);
  } else {
    console.error(`FAIL: Missing calibrated disclaimer in Box 5.`);
  }

  // Verify fallbacks exist in code
  if (html.includes('No secondary category assigned')) {
    console.log(`PASS: Explicit fallback "No secondary category assigned" present.`);
  } else {
    console.error(`FAIL: Missing fallback "No secondary category assigned".`);
  }

  if (html.includes('No Life-Saving Rule identified')) {
    console.log(`PASS: Explicit fallback "No Life-Saving Rule identified" present.`);
  } else {
    console.error(`FAIL: Missing fallback "No Life-Saving Rule identified".`);
  }

  // Verify Obsolete Titles are absent
  const obsoleteTitles = [
    'PRIMARY IOGP & REASONING',
    'SECONDARY IOGP & REASONING',
    'PRIMARY IOGP LIFE-SAVING RULE',
    'PRIMARY BARRIER DEFENSE & FAILURE MECHANISM',
    'SECONDARY BARRIER INTERACTION & CROSS-MAPPING',
    'IOGP REPORT 459 STANDARD COMPLIANCE AUDIT',
    'MANDATORY SAFEGUARD RESTORATION & ACTION PROTOCOL'
  ];

  let obsoleteFound = 0;
  obsoleteTitles.forEach(oldTitle => {
    if (html.includes(`<h3>${oldTitle}</h3>`)) {
      console.error(`FAIL: Obsolete title still present: "<h3>${oldTitle}</h3>"`);
      obsoleteFound++;
    }
  });

  if (obsoleteFound === 0) {
    console.log(`PASS: All obsolete IOGP box titles successfully absent.`);
  }

  // Check no separate sixth IOGP information box exists
  const totalIogpCardsInModal = (html.match(/id="iogpBox\d"/g) || []).length;
  if (totalIogpCardsInModal === 5) {
    console.log(`PASS: No extra or sixth IOGP information box present.`);
  } else {
    console.error(`FAIL: Unexpected number of IOGP boxes: ${totalIogpCardsInModal}`);
  }
}

verifyModalArchitecture('index.html');
verifyModalArchitecture('incident-classification.html');
