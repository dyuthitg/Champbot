import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { clsx } from 'clsx';

type ButtonVariant = 'primary' | 'success' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: ReactNode;
  children: ReactNode;
}

// One button set, four variants. Text colour is explicit on every one of
// them — white on the three solid variants, muted on ghost — never left to
// inherit from whatever the button happens to sit on top of.
const variants: Record<ButtonVariant, string> = {
  primary: 'bg-accent hover:bg-accent/85 text-white',
  success: 'bg-success hover:bg-success/85 text-white',
  danger: 'bg-transparent hover:bg-danger/10 text-danger-fg border border-danger/60',
  ghost: 'bg-transparent hover:bg-surface text-muted',
};

/** Routine actions (primary, success, ghost) are one tap. The danger
 * variant is visually set apart — outline instead of a filled block — so
 * a permanent action never reads as "just another button in the row." It
 * still needs its own confirm step at the call site; this only handles
 * how it looks, not whether it asks first. */
export function Button({ variant = 'ghost', icon, children, className, ...props }: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        variants[variant],
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

Button.displayName = 'Button';
