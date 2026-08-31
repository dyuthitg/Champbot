import type { ReactNode } from 'react';
import { clsx } from 'clsx';

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Left accent border for a state that needs to stand out in a list — a
   * flagged or blocked item, for example. Omit for a plain card. */
  accent?: 'none' | 'warning' | 'danger';
  padded?: boolean;
}

const accentBorder: Record<NonNullable<CardProps['accent']>, string> = {
  none: '',
  warning: 'border-l-2 border-l-accent',
  danger: 'border-l-2 border-l-danger',
};

/** The one card shape every queue item, section, and panel in the app uses. */
export function Card({ children, className, accent = 'none', padded = true }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-lg bg-surface/60 border border-border overflow-hidden',
        accentBorder[accent],
        padded && 'p-5',
        className,
      )}
    >
      {children}
    </div>
  );
}

Card.displayName = 'Card';
