export type IogpMetric = {
  id: string;
  name: string;
  incidents: number;
  iogpMatched: number;
  psifLinked: number;
  insufficient: number;
  sites: number;
};

export type ProcessedIogpMetric = IogpMetric & {
  psifRiskLinkage: number;
  psifShare: number;
  iogpMatchedShare: number;
  shortName: string;
};
