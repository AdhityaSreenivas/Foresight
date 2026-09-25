import React from 'react';
import {
  TOTAL_INCIDENTS,
  TOTAL_IOGP_MATCHED,
  TOTAL_PSIF_LINKED,
  TOTAL_INSUFFICIENT,
  formatCount,
  formatPercentage,
} from '../data/iogpData';

export const IogpSummaryCards: React.FC = () => {
  const iogpMatchPercent = formatPercentage((TOTAL_IOGP_MATCHED / TOTAL_INCIDENTS) * 100);
  const psifMatchPercent = formatPercentage((TOTAL_PSIF_LINKED / TOTAL_IOGP_MATCHED) * 100);
  const insufficientPercent = formatPercentage((TOTAL_INSUFFICIENT / TOTAL_INCIDENTS) * 100);

  const cards = [
    {
      id: 'total-incidents',
      label: 'TOTAL INCIDENTS',
      primaryValue: formatCount(TOTAL_INCIDENTS),
      description: 'All incident records analyzed',
      bottomText: '100% dataset coverage',
      topBorderColor: 'border-t-[#111827]',
    },
    {
      id: 'total-iogp-matched',
      label: 'TOTAL IOGP MATCHED',
      primaryValue: formatCount(TOTAL_IOGP_MATCHED),
      description: 'Incidents matched to IOGP rules',
      bottomText: `${iogpMatchPercent} of total incidents`,
      topBorderColor: 'border-t-[#2563EB]',
    },
    {
      id: 'psif-linked-matches',
      label: 'PSIF-LINKED MATCHES',
      primaryValue: formatCount(TOTAL_PSIF_LINKED),
      description: 'Matches with elevated PSIF risk',
      bottomText: `${psifMatchPercent} of IOGP matches`,
      topBorderColor: 'border-t-[#B91C1C]',
    },
    {
      id: 'insufficient-information',
      label: 'INSUFFICIENT INFORMATION',
      primaryValue: formatCount(TOTAL_INSUFFICIENT),
      description: 'Requires review or follow-up',
      bottomText: `${insufficientPercent} of total incidents`,
      topBorderColor: 'border-t-[#D97706]',
    },
  ];

  return (
    <section aria-label="Incident Summary Metrics" className="w-full min-w-0">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5 w-full min-w-0">
        {cards.map((card) => (
          <div
            key={card.id}
            className={`bg-white border border-[#E5E7EB] border-t-4 ${card.topBorderColor} rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] p-4 flex flex-col justify-between w-full min-w-0 box-border`}
          >
            <div>
              <span className="text-[11px] font-semibold text-[#6B7280] tracking-wider uppercase">
                {card.label}
              </span>
              <div className="text-2xl sm:text-[28px] font-bold text-[#111827] mt-1.5 mb-1 tracking-tight leading-none">
                {card.primaryValue}
              </div>
              <p className="text-xs text-[#6B7280]">{card.description}</p>
            </div>
            <div className="pt-2.5 mt-3 border-t border-[#E5E7EB] text-xs font-medium text-[#6B7280]">
              {card.bottomText}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
