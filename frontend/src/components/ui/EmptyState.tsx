import type { ReactNode } from 'react';
import { Button } from './Button';

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  body: string;
  cta?: { label: string; href?: string; onClick?: () => void };
}

/** Nothing waiting, no accounts connected, no campaigns yet — every empty
 * screen in the app says what happened and what to do next, never just
 * a blank page. */
export function EmptyState({ icon, title, body, cta }: EmptyStateProps) {
  return (
    <div className="max-w-2xl mx-auto px-4 py-20 text-center">
      <div className="mx-auto text-muted mb-4 [&>svg]:mx-auto" style={{ width: 40, height: 40 }}>
        {icon}
      </div>
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <p className="text-muted mt-2 text-sm">{body}</p>
      {cta && (
        <div className="mt-5 inline-flex">
          {cta.href ? (
            <a href={cta.href}>
              <Button variant="primary">{cta.label}</Button>
            </a>
          ) : (
            <Button variant="primary" onClick={cta.onClick}>
              {cta.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

EmptyState.displayName = 'EmptyState';
