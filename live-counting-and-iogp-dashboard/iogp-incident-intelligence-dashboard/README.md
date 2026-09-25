# IOGP Incident Intelligence Dashboard

A single-page industrial safety analytics dashboard built in **React + TypeScript + Tailwind CSS + Recharts**.

## Features
- **Dashboard Heading**: Clear hierarchy with subtitle and metadata.
- **4 Summary KPI Cards**: Total Incidents, Total IOGP Matched, PSIF-Linked Matches, Insufficient Information.
- **Top Comparison Chart**: Horizontal BarChart visualizing PSIF-Linked Matches across 9 IOGP barrier categories.
- **9 IOGP Metric Cards**: IOGP Matched, PSIF-Linked, Sites, PSIF Risk Linkage, and accessible progress bars.
- **3 Bottom Analytics Charts**:
  1. IOGP Matched Incidents by Category (Vertical Bar Chart)
  2. PSIF-Linked Match Distribution (Donut Chart with central counter)
  3. PSIF Risk Linkage by IOGP (Dark-Red Area Chart 0–100%)

## Quick Start (Already Includes Pre-installed node_modules)

### Running Dev Server
```bash
npm run dev
```
The dashboard will launch on [http://localhost:5173](http://localhost:5173).

### Building for Production
```bash
npm run build
```

### Previewing Production Build
```bash
npm run preview
```
Or simply open `dist/index.html` via a static HTTP server.
