import type { ReactNode } from 'react';
import { clsx } from 'clsx';

type ChipTone = 'neutral' | 'accent' | 'success' | 'danger';

interface ChipProps {
  children: ReactNode;
  tone?: ChipTone;
  icon?: ReactNode;
  className?: string;
}

// Text colour is set explicitly per tone, never inherited — see
// docs/CONTRAST_CHECK.md for why that rule exists and what it caught.
const tones: Record<ChipTone, string> = {
  neutral: 'bg-surface text-muted',
  accent: 'bg-accent/15 text-accent',
  success: 'bg-success/15 text-success',
  danger: 'bg-danger/15 text-danger',
};

/** A single fact, badge, or flag reason — relevance chips, quality
 * warnings, action-type labels, match scores. One line, no wrapping. */
export function Chip({ children, tone = 'neutral', icon, className }: ChipProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

Chip.displayName = 'Chip';
