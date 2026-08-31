/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Design tokens. Eight colours, five type sizes, four radii — the
      // set the Review Queue components need and nothing beyond it.
      // Contrast-checked against WCAG AA (4.5:1 text, 3:1 large text/UI) —
      // see docs/CONTRAST_CHECK.md for every pair and its ratio.
      colors: {
        // Base tokens referenced by index.css (@apply border-border, etc.).
        // Dark by default: deep navy canvas, slate cards, purple accent.
        border: '#334155',
        input: '#334155',
        ring: '#a855f7',
        background: '#0B0F19',
        foreground: '#e2e8f0',
        // --- the 8 tokens ---
        surface: '#1e293b',   // card / panel background (slate-800)
        muted: '#94a3b8',     // secondary text (slate-400)
        accent: '#a855f7',    // primary actions, focus, brand (purple-500)
        success: '#047857',   // approve / positive (emerald-700 — emerald-500 failed white-text contrast at 2.54:1)
        danger: '#ef4444',    // destructive / blocking (red-500)
        linkedin: {
          50: '#e7f3ff',
          100: '#d0e7ff',
          200: '#a8d4ff',
          300: '#74baff',
          400: '#3d95ff',
          500: '#0a66c2',
          600: '#004182',
          700: '#002e5f',
          800: '#001d3d',
          900: '#000f1f',
        },
      },
      // 5 type sizes. Named by role, not by pixel guesswork — every text
      // node in the Review Queue components picks one of these five.
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],       // 12px — meta, timestamps, chip labels
        sm: ['0.875rem', { lineHeight: '1.25rem' }],    // 14px — body default, buttons
        base: ['1rem', { lineHeight: '1.5rem' }],       // 16px — card titles
        lg: ['1.25rem', { lineHeight: '1.75rem' }],     // 20px — section headers
        xl: ['1.75rem', { lineHeight: '2.25rem' }],     // 28px — page titles
      },
      // 4px spacing scale: Tailwind's default spacing is already 4px-based
      // (1 = 4px, 2 = 8px, 3 = 12px, 4 = 16px, 6 = 24px, 8 = 32px) — adopted
      // as-is rather than redefined, so every existing className keeps working.
      borderRadius: {
        sm: '6px',
        md: '8px',
        lg: '12px',
        full: '9999px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
    },
  },
  plugins: [],
}
