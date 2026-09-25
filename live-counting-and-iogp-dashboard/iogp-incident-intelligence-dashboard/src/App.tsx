import React from 'react';
import { PROCESSED_IOGP_METRICS } from './data/iogpData';
import { IogpSummaryCards } from './components/IogpSummaryCards';
import { IogpComparisonChart } from './components/IogpComparisonChart';
import { IogpMetricCard } from './components/IogpMetricCard';
import { IncidentVolumeChart } from './components/IncidentVolumeChart';
import { IncidentDistributionChart } from './components/IncidentDistributionChart';
import { PsifLinkageChart } from './components/PsifLinkageChart';

export const App: React.FC = () => {
  return (
    <main className="min-h-screen bg-[#F7F8FA] py-6 sm:py-8 w-full max-w-[100vw] overflow-x-hidden box-border">
      <div className="max-w-[1440px] w-full mx-auto px-4 sm:px-6 lg:px-8 space-y-6 sm:space-y-7 min-w-0 box-border">
        {/* 1. PAGE HEADING */}
        <header className="mb-6">
          <h1 className="text-2xl sm:text-[28px] lg:text-[32px] font-bold text-[#111827] tracking-tight leading-tight">
            IOGP Incident Intelligence Dashboard
          </h1>
          <p className="text-sm sm:text-base text-[#6B7280] mt-1.5 leading-normal">
            Monitor IOGP rule matches, PSIF-linked incidents, and data sufficiency across barrier categories.
          </p>
        </header>

        {/* 2. FOUR SUMMARY CARDS */}
        <IogpSummaryCards />

        {/* 3. ONE PSIF-LINKED HORIZONTAL BAR CHART */}
        <IogpComparisonChart data={PROCESSED_IOGP_METRICS} />

        {/* 4. NINE IOGP METRIC CARDS */}
        <section aria-labelledby="barrier-portfolio-heading" className="w-full min-w-0">
          <header className="mb-4">
            <h2
              id="barrier-portfolio-heading"
              className="text-lg sm:text-xl font-bold text-[#111827] tracking-tight"
            >
              Barrier Intelligence Portfolio
            </h2>
            <p className="text-xs sm:text-sm text-[#6B7280] mt-1">
              Incident and PSIF linkage metrics across the nine IOGP barrier categories.
            </p>
          </header>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5 w-full min-w-0">
            {PROCESSED_IOGP_METRICS.map((metric) => (
              <IogpMetricCard key={metric.id} metric={metric} />
            ))}
          </div>
        </section>

        {/* 5. THREE BOTTOM CHARTS */}
        <section
          aria-label="Barrier Analytics Overview"
          className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5 w-full min-w-0"
        >
          <IncidentVolumeChart data={PROCESSED_IOGP_METRICS} />
          <IncidentDistributionChart data={PROCESSED_IOGP_METRICS} />
          <PsifLinkageChart data={PROCESSED_IOGP_METRICS} />
        </section>
      </div>
    </main>
  );
};

export default App;
