// A second-level tab strip for pages that fold two or three related screens
// together under one nav item. Deliberately styled as an underline, not a
// pill, so it never reads as another row of the primary nav above it.

import { clsx } from 'clsx';

export interface SubTab {
  key: string;
  label: string;
  icon?: React.ComponentType<{ size?: number | string }>;
}

export function SubTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: readonly SubTab[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-800 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={clsx(
              'flex items-center gap-1.5 shrink-0 whitespace-nowrap px-3 sm:px-4 min-h-[44px] sm:min-h-0 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              isActive
                ? 'border-purple-400 text-purple-300'
                : 'border-transparent text-slate-400 hover:text-slate-200',
            )}
          >
            {Icon && <Icon size={15} />}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
