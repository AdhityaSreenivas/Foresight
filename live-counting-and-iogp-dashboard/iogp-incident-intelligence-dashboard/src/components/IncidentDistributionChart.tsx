import React from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts';
import { ProcessedIogpMetric } from '../types';
import { TOTAL_PSIF_LINKED, formatCount, formatPercentage } from '../data/iogpData';

interface IncidentDistributionChartProps {
  data: ProcessedIogpMetric[];
}

const DONUT_COLORS = [
  '#B91C1C', // Dark red
  '#2563EB', // Blue
  '#DC2626', // Crimson
  '#3B82F6', // Medium blue
  '#64748B', // Slate neutral
  '#EF4444', // Red soft
  '#60A5FA', // Blue soft
  '#94A3B8', // Light slate
  '#1D4ED8', // Navy blue
];

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: ProcessedIogpMetric;
  }>;
}

const CustomDistributionTooltip: React.FC<CustomTooltipProps> = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const item = payload[0].payload;
    return (
      <div className="bg-white p-3 rounded-lg border border-[#E5E7EB] shadow-md text-xs sm:text-sm">
        <p className="font-semibold text-[#111827] mb-1">{item.name}</p>
        <div className="space-y-1 text-[#6B7280]">
          <div className="flex items-center justify-between gap-3">
            <span>PSIF-Linked Matches:</span>
            <span className="font-bold text-[#B91C1C]">{formatCount(item.psifLinked)}</span>
          </div>
          <div className="flex items-center justify-between gap-3 pt-1 border-t border-[#E5E7EB]">
            <span>Share of PSIF Matches:</span>
            <span className="font-bold text-[#111827]">{formatPercentage(item.psifShare)}</span>
          </div>
        </div>
      </div>
    );
  }
  return null;
};

export const IncidentDistributionChart: React.FC<IncidentDistributionChartProps> = ({ data }) => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 flex flex-col justify-between w-full min-w-0 box-border">
      <h3 className="font-semibold text-sm sm:text-base text-[#111827] mb-3">
        PSIF-Linked Match Distribution
      </h3>

      <div className="relative w-full h-[280px] sm:h-[300px]">
        {/* Total PSIF-linked matches placed in donut center */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl sm:text-2xl font-bold text-[#111827] tracking-tight">
            {formatCount(TOTAL_PSIF_LINKED)}
          </span>
          <span className="text-[10px] sm:text-[11px] uppercase tracking-wider text-[#6B7280] font-semibold mt-0.5">
            PSIF-Linked Matches
          </span>
        </div>

        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="psifLinked"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={68}
              outerRadius={98}
              paddingAngle={2}
              stroke="#FFFFFF"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {data.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={DONUT_COLORS[index % DONUT_COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomDistributionTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
