import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { ProcessedIogpMetric } from '../types';
import { formatCount, formatPercentage } from '../data/iogpData';

interface IogpComparisonChartProps {
  data: ProcessedIogpMetric[];
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: ProcessedIogpMetric;
  }>;
}

const CustomComparisonTooltip: React.FC<CustomTooltipProps> = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const item = payload[0].payload;
    return (
      <div className="bg-white p-3.5 rounded-lg border border-[#E5E7EB] shadow-md text-xs sm:text-sm">
        <p className="font-semibold text-[#111827] mb-2 border-b border-[#E5E7EB] pb-1.5">
          {item.name}
        </p>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-4">
            <span className="text-gray-600">IOGP Matched:</span>
            <span className="font-semibold text-[#111827]">{formatCount(item.iogpMatched)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-gray-600">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#B91C1C]" />
              PSIF-Linked Matches:
            </span>
            <span className="font-semibold text-[#B91C1C]">{formatCount(item.psifLinked)}</span>
          </div>
          <div className="flex items-center justify-between gap-4 pt-1 border-t border-[#E5E7EB] text-xs">
            <span className="text-gray-500">PSIF Risk Linkage:</span>
            <span className="font-bold text-[#B91C1C]">{formatPercentage(item.psifRiskLinkage)}</span>
          </div>
        </div>
      </div>
    );
  }
  return null;
};

export const IogpComparisonChart: React.FC<IogpComparisonChartProps> = ({ data }) => {
  // Sort categories by PSIF-linked matches descending
  const sortedData = [...data].sort((a, b) => b.psifLinked - a.psifLinked);

  return (
    <section className="bg-white border border-[#E5E7EB] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 sm:p-5 lg:p-6 w-full max-w-full min-w-0 overflow-hidden box-border">
      <header className="mb-4 sm:mb-5">
        <h2 className="text-lg sm:text-xl font-bold text-[#111827] tracking-tight">
          IOGP Barrier Risk Distribution Comparison
        </h2>
        <p className="text-xs sm:text-sm text-[#6B7280] mt-1">
          PSIF-linked incident matches across the nine IOGP barrier categories.
        </p>
      </header>

      {/* Overflow wrapper to preserve labels and full readability on narrow mobile screens */}
      <div className="w-full max-w-full min-w-0 overflow-x-auto pb-1">
        <div className="w-full min-w-[340px] sm:min-w-0 h-[480px] sm:h-[440px] lg:h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={sortedData}
              margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
              barGap={4}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                horizontal={false}
                vertical={true}
                stroke="#E5E7EB"
              />
              <XAxis
                type="number"
                tick={{ fill: '#6B7280', fontSize: 11 }}
                tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={{ stroke: '#E5E7EB' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={150}
                tick={{ fill: '#111827', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={{ stroke: '#E5E7EB' }}
              />
              <Tooltip
                content={<CustomComparisonTooltip />}
                cursor={{ fill: 'rgba(247, 248, 250, 0.6)' }}
              />
              <Legend
                verticalAlign="top"
                align="center"
                iconType="circle"
                wrapperStyle={{ paddingBottom: '16px', fontSize: '12px', color: '#111827' }}
              />
              <Bar
                dataKey="psifLinked"
                name="PSIF-Linked Matches"
                fill="#B91C1C"
                radius={[0, 4, 4, 0]}
                barSize={14}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
};
