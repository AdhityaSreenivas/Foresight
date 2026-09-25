import React from 'react';
import { ProcessedIogpMetric } from '../types';
import { formatCount, formatPercentage } from '../data/iogpData';

interface IogpMetricCardProps {
  metric: ProcessedIogpMetric;
}

export const IogpMetricCard: React.FC<IogpMetricCardProps> = ({ metric }) => {
  const percentageStr = formatPercentage(metric.psifRiskLinkage);
  const pillText = `${percentageStr} PSIF`;

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 flex flex-col justify-between w-full min-w-0 box-border transition-all duration-200 hover:border-gray-300">
      <div>
        {/* Card Header: Category Name & Pill Badge */}
        <div className="flex items-start justify-between gap-2.5 mb-3">
          <h3 className="font-semibold text-sm sm:text-[15px] text-[#111827] leading-snug">
            {metric.name}
          </h3>
          <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-[#B91C1C] border border-red-100">
            {pillText}
          </span>
        </div>

        {/* Divider */}
        <div className="border-t border-[#E5E7EB] mb-3" />

        {/* Three Evenly Spaced Metric Columns */}
        <div className="grid grid-cols-3 gap-2">
          <div>
            <div className="text-[10px] sm:text-[11px] font-semibold tracking-wider text-[#6B7280] uppercase">
              IOGP MATCHED
            </div>
            <div className="text-sm sm:text-[15px] font-bold text-[#111827] mt-1">
              {formatCount(metric.iogpMatched)}
            </div>
          </div>
          <div>
            <div className="text-[10px] sm:text-[11px] font-semibold tracking-wider text-[#6B7280] uppercase">
              PSIF-LINKED
            </div>
            <div className="text-sm sm:text-[15px] font-bold text-[#B91C1C] mt-1">
              {formatCount(metric.psifLinked)}
            </div>
          </div>
          <div>
            <div className="text-[10px] sm:text-[11px] font-semibold tracking-wider text-[#6B7280] uppercase">
              SITES
            </div>
            <div className="text-sm sm:text-[15px] font-bold text-[#111827] mt-1">
              {formatCount(metric.sites)}
            </div>
          </div>
        </div>
      </div>

      <div>
        {/* Divider */}
        <div className="border-t border-[#E5E7EB] my-3" />

        {/* PSIF Risk Linkage Row */}
        <div className="flex items-center justify-between text-xs sm:text-[13px] font-medium mb-1.5">
          <span className="text-[#6B7280]">PSIF Risk Linkage</span>
          <span className="font-bold text-[#B91C1C]">{percentageStr}</span>
        </div>

        {/* Accessible Slim Progress Bar */}
        <div
          role="progressbar"
          aria-valuenow={parseFloat(metric.psifRiskLinkage.toFixed(1))}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${metric.name} PSIF Risk Linkage`}
          className="w-full bg-gray-100 rounded-full h-[7px] overflow-hidden"
        >
          <div
            className="bg-[#B91C1C] h-full rounded-full transition-all duration-300"
            style={{ width: `${Math.min(100, Math.max(0, metric.psifRiskLinkage))}%` }}
          />
        </div>
      </div>
    </div>
  );
};
