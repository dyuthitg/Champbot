import type { ReactNode } from 'react';
import { clsx } from 'clsx';

type ChipTone = 'neutral' | 'accent' | 'success' | 'warn' | 'danger';

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
  // -fg, not the fill: a chip is text on a tint of its own colour, and the
  // fills are chosen to sit *under* white. Measured on the composited chip
  // background — success 6.72:1, danger 4.63:1, warn 5.20:1.
  success: 'bg-success/15 text-success-fg',
  warn: 'bg-warn/15 text-warn',
  danger: 'bg-danger/15 text-danger-fg',
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
