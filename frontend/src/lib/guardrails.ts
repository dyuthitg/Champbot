// Guardrail display rules for the review queue.
//
// The *names* of the rules are deliberately not in this file. Every label an
// operator reads ("Too long", "Generic phrase", "No specific reference")
// arrives from the API, sourced from the rule table in
// src/outreach/quality.py, so there is exactly one place a rule is named and
// the queue cannot drift out of step with the spec.
//
// What is here is the display side of that: which colour a severity gets, and
// the character limits the live counter needs before the server has seen a
// single keystroke. Those numbers mirror src/outreach/quality.py and are
// pinned by tests/test_guardrail_flags.py, which reads this file and
// fails if the two ever disagree.

import type { QualityFlag, SuggestionAction } from '@/types';

/** Mirrors CONNECT_NOTE_MAX / COMMENT_MAX / MESSAGE_MAX in quality.py — the
 *  number that actually blocks an approval. */
export const HARD_LIMIT: Partial<Record<SuggestionAction, number>> = {
  connect: 300,
  comment: 400,
  message: 900,
};

/** The number the written rule asks for, where it is stricter than the number
 *  the code enforces. Comments: 280 (spec R2). Messages: 600
 *  (MESSAGE_IDEAL_MAX). Crossing this is amber, not red — the gate lets it
 *  through, and a counter that lied about that would just get ignored. */
export const SOFT_TARGET: Partial<Record<SuggestionAction, number>> = {
  comment: 280,
  message: 600,
};

/** R1: a comment is 1–3 sentences. */
export const SENTENCE_MAX = 3;

/** quality.py's count_sentences(), same test: split on . ! ? and count the
 *  non-empty pieces. Runs on every keystroke, so it stays this cheap. */
export function countSentences(text: string): number {
  return text.split(/[.!?]+/).filter((part) => part.trim().length > 0).length;
}

export type CounterTone = 'muted' | 'warn' | 'danger';

export interface LengthReading {
  chars: number;
  sentences: number;
  hardLimit?: number;
  softTarget?: number;
  tone: CounterTone;
  /** Why it is amber or red, in one short phrase. Empty when nothing is wrong. */
  note: string;
  /** True once the copy can no longer be approved. */
  overHardLimit: boolean;
}

/**
 * What the counter under the editor should say right now.
 *
 * Three states, not two: under the target (quiet), past the written rule but
 * still sendable (amber — you can still fix this), and past the enforced cap
 * (red, and Approve goes away). Amber is the whole point: catching a comment
 * at 290 characters costs nothing, rejecting it at 410 costs a review cycle.
 */
export function readLength(text: string, action: SuggestionAction): LengthReading {
  // Trimmed, because the gate trims before it measures. An untrimmed count
  // reads one character higher than the number in the flag underneath it,
  // and a counter that disagrees with the rule it is counting against is
  // worse than no counter.
  const trimmed = text.trim();
  const chars = trimmed.length;
  const sentences = countSentences(trimmed);
  const hardLimit = HARD_LIMIT[action];
  const softTarget = SOFT_TARGET[action];

  if (hardLimit && chars > hardLimit) {
    return {
      chars, sentences, hardLimit, softTarget,
      tone: 'danger',
      note: `over the ${hardLimit}-character limit — can't be approved`,
      overHardLimit: true,
    };
  }
  if (softTarget && chars > softTarget) {
    return {
      chars, sentences, hardLimit, softTarget,
      tone: 'warn',
      note: `over the ${softTarget}-character target`,
      overHardLimit: false,
    };
  }
  if (action === 'comment' && sentences > SENTENCE_MAX) {
    return {
      chars, sentences, hardLimit, softTarget,
      tone: 'warn',
      note: `${sentences} sentences — the rule is 1 to ${SENTENCE_MAX}`,
      overHardLimit: false,
    };
  }
  // "Near the cap" — the last 10% before whichever number bites first.
  const nextNumber = softTarget ?? hardLimit;
  if (nextNumber && chars >= nextNumber * 0.9) {
    return {
      chars, sentences, hardLimit, softTarget,
      tone: 'warn',
      note: `close to the ${nextNumber}-character ${softTarget ? 'target' : 'limit'}`,
      overHardLimit: false,
    };
  }
  return { chars, sentences, hardLimit, softTarget, tone: 'muted', note: '', overHardLimit: false };
}

/** Blockers first, then warnings, then advisories: the order an operator
 *  should read them in, since only the first kind stops an approval. */
const SEVERITY_ORDER: Record<QualityFlag['severity'], number> = {
  blocker: 0,
  warning: 1,
  advisory: 2,
};

export function sortFlags(flags: QualityFlag[]): QualityFlag[] {
  return [...flags].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || a.code.localeCompare(b.code),
  );
}

export function chipTone(severity: QualityFlag['severity']): 'danger' | 'warn' | 'neutral' {
  if (severity === 'blocker') return 'danger';
  if (severity === 'warning') return 'warn';
  return 'neutral';
}

/** Plain-English gloss of what a severity means, used in tooltips and the
 *  filter bar's legend. Nobody should have to learn our jargon to use this. */
export const SEVERITY_MEANING: Record<QualityFlag['severity'], string> = {
  blocker: "Can't be approved until this is fixed",
  warning: 'Costs quality score — usually worth a rewrite',
  advisory: 'Breaks a written rule the gate does not yet enforce',
};

export const SEVERITY_LABEL: Record<QualityFlag['severity'], string> = {
  blocker: 'Blocked',
  warning: 'Warning',
  advisory: 'Advisory',
};

export interface FlagBucket {
  code: string;
  label: string;
  severity: QualityFlag['severity'];
  count: number;
  specRef?: string | null;
}

/**
 * Every failure type present in this queue, with how many items have it.
 *
 * This is what makes batching possible: an operator who can see "Generic
 * phrase — 14" can fix fourteen of the same mistake in one pass instead of
 * meeting them one at a time in date order.
 */
export function bucketFlags(
  items: { quality_flags?: QualityFlag[] }[],
): FlagBucket[] {
  const buckets = new Map<string, FlagBucket>();
  for (const item of items) {
    // One item counts once per rule, even if it breaks that rule twice.
    const seen = new Set<string>();
    for (const flag of item.quality_flags ?? []) {
      if (seen.has(flag.code)) continue;
      seen.add(flag.code);
      const existing = buckets.get(flag.code);
      if (existing) {
        existing.count += 1;
        // Worst severity wins the bucket's colour.
        if (SEVERITY_ORDER[flag.severity] < SEVERITY_ORDER[existing.severity]) {
          existing.severity = flag.severity;
        }
      } else {
        buckets.set(flag.code, {
          code: flag.code,
          label: flag.label,
          severity: flag.severity,
          count: 1,
          specRef: flag.spec_ref,
        });
      }
    }
  }
  return [...buckets.values()].sort(
    (a, b) =>
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
      b.count - a.count ||
      a.code.localeCompare(b.code),
  );
}

/** The worst thing wrong with an item, for sorting the queue by failure. */
export function worstSeverity(flags: QualityFlag[] = []): number {
  return flags.reduce((worst, f) => Math.min(worst, SEVERITY_ORDER[f.severity]), 3);
}
