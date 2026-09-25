import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { ProcessedIogpMetric } from '../types';
import { formatPercentage } from '../data/iogpData';

interface PsifLinkageChartProps {
  data: ProcessedIogpMetric[];
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: ProcessedIogpMetric;
  }>;
}

const CustomLinkageTooltip: React.FC<CustomTooltipProps> = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const item = payload[0].payload;
    return (
      <div className="bg-white p-3 rounded-lg border border-[#E5E7EB] shadow-md text-xs sm:text-sm">
        <p className="font-semibold text-[#111827] mb-1">{item.name}</p>
        <div className="flex items-center gap-2 text-[#6B7280]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#B91C1C]" />
          <span>PSIF Risk Linkage:</span>
          <span className="font-bold text-[#B91C1C]">{formatPercentage(item.psifRiskLinkage)}</span>
        </div>
      </div>
    );
  }
  return null;
};

export const PsifLinkageChart: React.FC<PsifLinkageChartProps> = ({ data }) => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 flex flex-col justify-between w-full min-w-0 box-border">
      <h3 className="font-semibold text-sm sm:text-base text-[#111827] mb-3">
        PSIF Risk Linkage by IOGP
      </h3>

      <div className="w-full h-[280px] sm:h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 10, right: 10, left: -15, bottom: 25 }}
          >
            <defs>
              <linearGradient id="psifGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#B91C1C" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#B91C1C" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              horizontal={true}
              stroke="#E5E7EB"
            />
            <XAxis
              dataKey="shortName"
              tick={{ fill: '#6B7280', fontSize: 11 }}
              interval={0}
              angle={-35}
              textAnchor="end"
              height={45}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: '#6B7280', fontSize: 11 }}
              tickFormatter={(value) => `${value}%`}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={{ stroke: '#E5E7EB' }}
            />
            <Tooltip content={<CustomLinkageTooltip />} />
            <Area
              type="monotone"
              dataKey="psifRiskLinkage"
              stroke="#B91C1C"
              strokeWidth={2.5}
              fill="url(#psifGradient)"
              dot={{ fill: '#B91C1C', r: 3.5, strokeWidth: 1.5, stroke: '#FFFFFF' }}
              activeDot={{ r: 6, fill: '#B91C1C', stroke: '#FFFFFF', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
