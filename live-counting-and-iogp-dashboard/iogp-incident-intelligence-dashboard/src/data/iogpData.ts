import { IogpMetric, ProcessedIogpMetric } from '../types';

export const RAW_IOGP_METRICS: IogpMetric[] = [
  {
    id: 'safe-mechanical-lifting',
    name: 'Safe Mechanical Lifting',
    incidents: 104280,
    iogpMatched: 94895,
    psifLinked: 59440,
    insufficient: 9385,
    sites: 138,
  },
  {
    id: 'energy-isolation',
    name: 'Energy Isolation',
    incidents: 132450,
    iogpMatched: 121854,
    psifLinked: 84768,
    insufficient: 10596,
    sites: 142,
  },
  {
    id: 'driving',
    name: 'Driving',
    incidents: 34500,
    iogpMatched: 31740,
    psifLinked: 18975,
    insufficient: 2760,
    sites: 110,
  },
  {
    id: 'hot-work',
    name: 'Hot Work',
    incidents: 78340,
    iogpMatched: 70506,
    psifLinked: 36036,
    insufficient: 7834,
    sites: 115,
  },
  {
    id: 'working-at-height',
    name: 'Working at Height',
    incidents: 92610,
    iogpMatched: 84275,
    psifLinked: 48157,
    insufficient: 8335,
    sites: 124,
  },
  {
    id: 'confined-space',
    name: 'Confined Space',
    incidents: 64800,
    iogpMatched: 59616,
    psifLinked: 44712,
    insufficient: 5184,
    sites: 98,
  },
  {
    id: 'line-of-fire',
    name: 'Line of Fire',
    incidents: 118920,
    iogpMatched: 109406,
    psifLinked: 72541,
    insufficient: 9514,
    sites: 156,
  },
  {
    id: 'work-authorization',
    name: 'Work Authorization',
    incidents: 56120,
    iogpMatched: 49947,
    psifLinked: 21326,
    insufficient: 6173,
    sites: 162,
  },
  {
    id: 'bypassing-safety-controls',
    name: 'Bypassing Safety Controls',
    incidents: 43750,
    iogpMatched: 38938,
    psifLinked: 25375,
    insufficient: 4812,
    sites: 84,
  },
];

const SHORT_NAMES: Record<string, string> = {
  'Safe Mechanical Lifting': 'Lifting',
  'Energy Isolation': 'Isolation',
  'Driving': 'Driving',
  'Hot Work': 'Hot Work',
  'Working at Height': 'Height',
  'Confined Space': 'Confined',
  'Line of Fire': 'Line of Fire',
  'Work Authorization': 'Work Auth',
  'Bypassing Safety Controls': 'Bypass Controls',
};

// Summary totals derived programmatically
export const TOTAL_INCIDENTS = RAW_IOGP_METRICS.reduce((sum, item) => sum + item.incidents, 0);
export const TOTAL_IOGP_MATCHED = RAW_IOGP_METRICS.reduce((sum, item) => sum + item.iogpMatched, 0);
export const TOTAL_PSIF_LINKED = RAW_IOGP_METRICS.reduce((sum, item) => sum + item.psifLinked, 0);
export const TOTAL_INSUFFICIENT = RAW_IOGP_METRICS.reduce((sum, item) => sum + item.insufficient, 0);

// Programmatically processed metrics with derived rates
export const PROCESSED_IOGP_METRICS: ProcessedIogpMetric[] = RAW_IOGP_METRICS.map((item) => ({
  ...item,
  psifRiskLinkage: (item.psifLinked / item.iogpMatched) * 100,
  psifShare: (item.psifLinked / TOTAL_PSIF_LINKED) * 100,
  iogpMatchedShare: (item.iogpMatched / TOTAL_IOGP_MATCHED) * 100,
  shortName: SHORT_NAMES[item.name] || item.name,
}));

// Number and percentage formatters
const numberFormatter = new Intl.NumberFormat('en-US');

export const formatCount = (value: number): string => {
  return numberFormatter.format(value);
};

export const formatPercentage = (value: number): string => {
  return `${value.toFixed(1)}%`;
};
