import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { ProcessedIogpMetric } from '../types';
import { formatCount } from '../data/iogpData';

interface IncidentVolumeChartProps {
  data: ProcessedIogpMetric[];
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: ProcessedIogpMetric;
  }>;
}

const CustomVolumeTooltip: React.FC<CustomTooltipProps> = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const item = payload[0].payload;
    return (
      <div className="bg-white p-3 rounded-lg border border-[#E5E7EB] shadow-md text-xs sm:text-sm">
        <p className="font-semibold text-[#111827] mb-1">{item.name}</p>
        <div className="flex items-center gap-2 text-[#6B7280]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#2563EB]" />
          <span>IOGP Matched:</span>
          <span className="font-bold text-[#111827]">{formatCount(item.iogpMatched)}</span>
        </div>
      </div>
    );
  }
  return null;
};

export const IncidentVolumeChart: React.FC<IncidentVolumeChartProps> = ({ data }) => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 flex flex-col justify-between w-full min-w-0 box-border">
      <h3 className="font-semibold text-sm sm:text-base text-[#111827] mb-3">
        IOGP Matched Incidents by Category
      </h3>

      <div className="w-full h-[280px] sm:h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 10, right: 10, left: -15, bottom: 25 }}
          >
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
              tick={{ fill: '#6B7280', fontSize: 11 }}
              tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={{ stroke: '#E5E7EB' }}
            />
            <Tooltip
              content={<CustomVolumeTooltip />}
              cursor={{ fill: 'rgba(247, 248, 250, 0.6)' }}
            />
            <Bar
              dataKey="iogpMatched"
              fill="#2563EB"
              radius={[4, 4, 0, 0]}
              barSize={18}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
