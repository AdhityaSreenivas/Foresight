/* ==========================================================================
   FORESIGHT — Unified Frontend Workspace Script
   Industrial HSSE Decision-Support & Operational Precursor Intelligence
   ========================================================================== */

// ── Canonical Operational Activity Data (1,000 records) ────────────────────────
const ACTIVITIES_DATA = [
    {
        rank: 1,
        name: "Vehicle / Parking Operations",
        incidents: 140,
        psif: 27,
        rate: 19.3,
        share: 14.0,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Segregation Barrier / Wheel Chock",
        associated_iogp: "Driving",
        narratives: [
            "Forklift reversing in loading yard struck staging rack after driver lost sight of mirror perimeter.",
            "Light transport vehicle tire caught curb while maneuvering near compressor manifold bay.",
            "Flatbed delivery truck braked abruptly; unsecured pipe spools shifted into cabin rack."
        ]
    },
    {
        rank: 2,
        name: "Work at Height / Scaffolding",
        incidents: 133,
        psif: 28,
        rate: 21.1,
        share: 13.3,
        top_location: "Pipe Rack / Manifold",
        top_barrier: "Safety Harness / Fall Protection",
        associated_iogp: "Working at Height",
        narratives: [
            "Scaffolder modifying top grating detached dual lanyard; harness caught worker during slip.",
            "Ladder base slipped on wet platform during valve inspection at high elevation.",
            "Erected scaffold platform found missing toe boards along northern boundary."
        ]
    },
    {
        rank: 3,
        name: "Lifting Operation / Crane Work",
        incidents: 129,
        psif: 13,
        rate: 10.1,
        share: 12.9,
        top_location: "Process Area / Refining Unit",
        top_barrier: "Certified Rigging / Whip Check",
        associated_iogp: "Safe Mechanical Lifting",
        narratives: [
            "Mobile crane hook swung near piperack structure while hoisting heat exchanger bundle.",
            "Rigging sling showed minor abrasive wear during pre-lift inspection; replaced prior to tandem lift.",
            "Winch cable tension released unexpectedly during valve lowering into sump pit."
        ]
    },
    {
        rank: 4,
        name: "Equipment Maintenance & Servicing",
        incidents: 127,
        psif: 9,
        rate: 7.1,
        share: 12.7,
        top_location: "Process Area / Refining Unit",
        top_barrier: "Lockout / Tagout (LOTO)",
        associated_iogp: "Energy Isolation",
        narratives: [
            "Centrifugal pump overhaul commenced; lockout locks in place and verified zero pressure.",
            "Filter replacement on fuel gas train; minor residual odor detected before purging complete.",
            "Gearbox alignment checked on cooling water pump; safety interlock verified before re-energizing."
        ]
    },
    {
        rank: 5,
        name: "Internal Vessel Cleaning & Inspection",
        incidents: 106,
        psif: 20,
        rate: 18.9,
        share: 10.6,
        top_location: "Tank Farm / Crude Storage",
        top_barrier: "Forced Air Ventilation & Gas Detector",
        associated_iogp: "Confined Space",
        narratives: [
            "Sludge cleanout inside crude storage tank; continuous mechanical ventilation maintained.",
            "Column tray internal inspection conducted under confined-space work authorization.",
            "Atmospheric monitor alarmed on low oxygen inside knockout drum prior to scheduled entry."
        ]
    },
    {
        rank: 6,
        name: "Welding, Cutting & Hot Work",
        incidents: 90,
        psif: 0,
        rate: 0.0,
        share: 9.0,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Fire Watch & Gas Detector",
        associated_iogp: "Hot Work",
        narratives: [
            "Structural steel welding in workshop bay; spark containment tarpaulin properly installed.",
            "Oxy-acetylene cutting torch torch flame extinguished immediately when flash-back arrestor seated.",
            "TIG welding of stainless pipe spool; continuous 4-gas atmospheric monitoring showed 0% LEL."
        ]
    },
    {
        rank: 7,
        name: "Pipeline Maintenance & Valve Work",
        incidents: 64,
        psif: 7,
        rate: 10.9,
        share: 6.4,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Isolation Valve / Mechanical Blind",
        associated_iogp: "Line of Fire",
        narratives: [
            "Flange bolt torqueing on hydrocarbon transfer header; whip-check safety cable secured.",
            "Valve greasing on crude manifold; technicians stood clear of high-pressure injection fitting.",
            "Pig receiver door opened after positive bleed verification; minor condensate captured in tray."
        ]
    },
    {
        rank: 8,
        name: "Electrical Maintenance & Troubleshooting",
        incidents: 62,
        psif: 10,
        rate: 16.1,
        share: 6.2,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Arc Flash Suit & Isolation Switch",
        associated_iogp: "Bypassing Safety Controls",
        narratives: [
            "Switchgear 415V breaker racking; technician wore certified arc-flash shield as required.",
            "Control panel wiring troubleshooting; multimeter lead touched grounded frame causing minor trip.",
            "Emergency battery bank testing completed; eyewash station verified operational before work."
        ]
    },
    {
        rank: 9,
        name: "Digging / Excavation",
        incidents: 59,
        psif: 6,
        rate: 10.2,
        share: 5.9,
        top_location: "Process Area / Refining Unit",
        top_barrier: "Trench Shoring & Underground Utility Scan",
        associated_iogp: "Work Authorization",
        narratives: [
            "Trench excavated to 1.8m depth; hydraulic shoring box installed before technician entry.",
            "Excavator bucket touched shallow instrument conduit tile; excavation halted immediately.",
            "Hand digging conducted within 1 meter of marked pipeline route per work permit requirements."
        ]
    },
    {
        rank: 10,
        name: "Painting & Surface Coating",
        incidents: 30,
        psif: 20,
        rate: 66.7,
        share: 3.0,
        top_location: "Process Area / Refining Unit",
        top_barrier: "Gas Detector & Respirator",
        associated_iogp: "Hot Work",
        narratives: [
            "Abrasive blasting of tank exterior; operators wore supplied-air blast helmets.",
            "Airless spray painting of structural pipe supports in process area; gas detector nearby.",
            "Primer application using brushes on flare line staircase; fall protection secured."
        ]
    },
    {
        rank: 11,
        name: "Cleaning & Housekeeping",
        incidents: 20,
        psif: 20,
        rate: 100.0,
        share: 2.0,
        top_location: "Compressor Area",
        top_barrier: "Spill Containment & Absorbent Booms",
        associated_iogp: "Energy Isolation",
        narratives: [
            "Workshop floor degreasing and cleaning after valve servicing; absorbent pads deployed.",
            "Oily condensate swept from compressor bay drainage trough into sump collector.",
            "Washdown of separator skid perimeter; walkways cleared of hoses to prevent tripping."
        ]
    },
    {
        rank: 12,
        name: "Inspection & Quality Auditing",
        incidents: 15,
        psif: 15,
        rate: 100.0,
        share: 1.5,
        top_location: "Process Area / Refining Unit",
        top_barrier: "Personal Protective Equipment",
        associated_iogp: "Line of Fire",
        narratives: [
            "NDT ultrasonic thickness gauging on high-pressure steam line elbow.",
            "Visual weld quality audit performed on newly installed pipeline spool.",
            "Pre-commissioning walk-down conducted on crude booster pump station."
        ]
    },
    {
        rank: 13,
        name: "Material Handling & Staging",
        incidents: 15,
        psif: 15,
        rate: 100.0,
        share: 1.5,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Pallet Jack Interlock & Steel-Toe Boots",
        associated_iogp: "Safe Mechanical Lifting",
        narratives: [
            "Manual staging of nitrogen cylinders on transport pallets in warehouse dock.",
            "Drum lifting clamp used to stage corrosion inhibitor drums in chemical yard.",
            "Crated mechanical parts moved using hydraulic hand pallet truck."
        ]
    },
    {
        rank: 14,
        name: "Laboratory / Research",
        incidents: 10,
        psif: 10,
        rate: 100.0,
        share: 1.0,
        top_location: "Workshop / Maintenance Bay",
        top_barrier: "Fume Hood & Chemical Goggles",
        associated_iogp: "Work Authorization",
        narratives: [
            "Crude oil sample titration conducted inside certified laboratory fume hood.",
            "Glassware cleaning with solvent carried out under ventilation duct.",
            "Produced water hydrocarbon analysis using benchtop spectrophotometer."
        ]
    }
];

let currentActivityMetric = "incident"; // "incident" or "psif"

// ── View Switching Logic ──────────────────────────────────────────────────────
function switchView(viewId) {
    document.querySelectorAll(".view-container").forEach(v => v.classList.remove("active"));
    document.querySelectorAll(".sidebar-nav-item").forEach(item => item.classList.remove("active"));
    
    const target = document.getElementById(viewId);
    if (target) {
        target.classList.add("active");
    }

    // Set page header title
    const titles = {
        "view-dashboard": "Operational Precursor Intelligence Overview",
        "view-pattern-hub": "Pattern Intelligence Hub",
        "view-activity": "Activity Pattern Analysis",
        "view-barrier": "Barrier Intelligence & Safeguards",
        "view-location": "Spatial Location Heatmap",
        "view-submit": "Submit Incident Report",
        "view-upload": "Batch Dataset Intake",
        "view-adjudication": "Human-in-the-Loop Adjudication",
        "view-model-review": "PSIF Model Assurance"
    };

    if (titles[viewId]) {
        document.getElementById("current-view-title").textContent = titles[viewId];
    }
}

// ── Render Activity Ranking Bars ──────────────────────────────────────────────
function renderActivityBars() {
    const container = document.getElementById("activity-bars-container");
    if (!container) return;

    container.innerHTML = "";

    const maxVal = currentActivityMetric === "incident" 
        ? Math.max(...ACTIVITIES_DATA.map(a => a.incidents))
        : Math.max(...ACTIVITIES_DATA.map(a => a.psif));

    ACTIVITIES_DATA.forEach((act, idx) => {
        const val = currentActivityMetric === "incident" ? act.incidents : act.psif;
        const pct = ((val / maxVal) * 100).toFixed(1);
        const barColor = currentActivityMetric === "incident" ? "#38bdf8" : "#ef4444";

        const row = document.createElement("div");
        row.className = "ranking-bar-row";
        row.onclick = () => openActivityModal(idx);

        row.innerHTML = `
            <span class="rank-num">${idx + 1}</span>
            <div style="width: 260px; font-weight: 700; color: #f8fafc; font-size: 0.9rem;">${act.name}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width: ${pct}%; background: ${barColor};"></div>
            </div>
            <span style="font-family: monospace; font-size: 0.88rem; font-weight: 700; color: #f8fafc; width: 65px; text-align: right;">
                ${val} ${currentActivityMetric === "incident" ? "obs" : "PSIF"}
            </span>
            <span class="badge" style="background: ${act.psif > 0 ? '#ef4444' : '#334155'}; color: ${act.psif > 0 ? '#fff' : '#94a3b8'}; font-size: 0.72rem; width: 110px; text-align: center;">
                ${act.psif} PSIF (${act.rate}%)
            </span>
        `;
        container.appendChild(row);
    });
}

// ── Render Activity Portfolio Table ───────────────────────────────────────────
function renderActivityTable() {
    const tbody = document.getElementById("activity-table-body");
    if (!tbody) return;

    tbody.innerHTML = "";

    ACTIVITIES_DATA.forEach((act, idx) => {
        const tr = document.createElement("tr");
        tr.style.borderBottom = "1px solid #334155";

        tr.innerHTML = `
            <td style="padding: 0.75rem 0.5rem; text-align: center; font-weight: 700; color: #94a3b8;">${act.rank}</td>
            <td style="padding: 0.75rem 0.75rem;">
                <div style="font-weight: 800; color: #f8fafc;">${act.name}</div>
                <div style="font-size: 0.72rem; color: #10b981; font-weight: 600;">&bull; Recurring Pattern (&ge;2 obs)</div>
            </td>
            <td style="padding: 0.75rem 0.65rem; text-align: right; font-family: monospace; font-weight: 700;">
                <div>${act.incidents}</div>
                <div style="font-size: 0.72rem; color: #64748b;">${act.share}%</div>
            </td>
            <td style="padding: 0.75rem 0.65rem; text-align: right; font-family: monospace; font-weight: 700; color: ${act.psif > 0 ? '#ef4444' : '#64748b'};">
                ${act.psif}
            </td>
            <td style="padding: 0.75rem 0.65rem; text-align: right; font-family: monospace; font-weight: 700; color: #38bdf8;">
                ${act.rate}%
            </td>
            <td style="padding: 0.75rem 0.75rem;">
                <span class="association-tag location">${act.top_location}</span>
            </td>
            <td style="padding: 0.75rem 0.75rem;">
                <span class="association-tag barrier">${act.top_barrier}</span>
            </td>
            <td style="padding: 0.75rem 0.75rem;">
                <span class="association-tag iogp">${act.associated_iogp}</span>
            </td>
            <td style="padding: 0.75rem 0.5rem; text-align: center;">
                <button class="btn btn-secondary" onclick="openActivityModal(${idx})" style="padding: 0.35rem 0.75rem; font-size: 0.76rem;">Inspect</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ── Metric Toggle Switch ──────────────────────────────────────────────────────
function setActivityMetric(metric) {
    currentActivityMetric = metric;
    document.getElementById("btn-toggle-incident-vol").classList.toggle("active", metric === "incident");
    document.getElementById("btn-toggle-psif-vol").classList.toggle("active", metric === "psif");
    renderActivityBars();
}

// ── Activity Modal Details ────────────────────────────────────────────────────
function openActivityModal(idx) {
    const act = ACTIVITIES_DATA[idx];
    if (!act) return;

    document.getElementById("modal-activity-title").textContent = act.name;
    document.getElementById("modal-incident-count").textContent = act.incidents;
    document.getElementById("modal-psif-count").textContent = act.psif;
    document.getElementById("modal-psif-rate").textContent = act.rate + "%";

    const assocContainer = document.getElementById("modal-associations");
    assocContainer.innerHTML = `
        <span class="association-tag location">Top Location: ${act.top_location}</span>
        <span class="association-tag barrier">Primary Barrier: ${act.top_barrier}</span>
        <span class="association-tag iogp">Life-Saving Rule: ${act.associated_iogp}</span>
    `;

    const narrContainer = document.getElementById("modal-narrative-excerpts");
    narrContainer.innerHTML = act.narratives.map(n => `
        <div style="background: #0f172a; padding: 0.75rem; border-radius: 4px; border-left: 3px solid #38bdf8; font-size: 0.85rem; color: #f8fafc; line-height: 1.5;">
            "${n}"
        </div>
    `).join("");

    document.getElementById("activity-detail-modal").classList.add("open");
}

function closeActivityModal(e) {
    document.getElementById("activity-detail-modal").classList.remove("open");
}

// ── Location Zone Selection ───────────────────────────────────────────────────
function selectZone(name, total, psif, desc) {
    document.querySelectorAll(".zone-card").forEach(c => c.classList.remove("active"));
    if (event && event.currentTarget) {
        event.currentTarget.classList.add("active");
    }

    document.getElementById("selected-zone-name").textContent = name;
    document.getElementById("selected-zone-total").textContent = total;
    document.getElementById("selected-zone-psif").textContent = `${psif} PSIF Observations`;
    document.getElementById("selected-zone-desc").textContent = desc;
    document.getElementById("selected-zone-rate").textContent = ((psif / total) * 100).toFixed(1) + "%";
}

// ── Pre-fill SIF Precursor Scenario ───────────────────────────────────────────
function prefillPrecursorScenario() {
    document.getElementById("form-incident-date").value = "2026-03-03";
    document.getElementById("form-location").value = "Compressor Area";
    document.getElementById("form-job-task").value = "Pressure-Line Maintenance / Flange Breaking";
    document.getElementById("form-equipment").value = "Reciprocating Compressor Stage-2 Discharge Manifold";
    document.getElementById("form-narrative").value = "During planned flange breaking on the discharge piping manifold of Compressor K-201, technicians unbolted the final stud without completing the dual-isolation bleed verification. Trapped hydrocarbon gas under 42 bar pressure released violently, causing high-energy gas cloud dispersion. Fortunately, personal H2S gas detectors alarmed instantly and the crew evacuated to the muster point with zero injuries.";
    alert("Pre-fill scenario loaded: High-Energy Pressure Release (SIF Precursor Candidate).");
}

function submitDemoIncident() {
    alert("Incident successfully submitted and processed via deterministic PSIF rule reasoning! Metric counters updated.");
    switchView("view-dashboard");
}

function resetWorkspaceDemo() {
    if (confirm("Reset workspace to clean-sheet demonstration baseline?")) {
        alert("Workspace reset to initial 1,000 incident state.");
        switchView("view-dashboard");
    }
}

// ── Initialize on Load ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    renderActivityBars();
    renderActivityTable();
});
