// The approval queue.
//
// This is the screen the product is built around: the agent proposes who to
// contact and what to say, and a human decides. Every card has to answer three
// questions fast — who is this person, why them, and is this message something
// I'd be happy to have sent under my name.

import { useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Ban,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  MessageSquare,
  Pencil,
  Quote,
  PlugZap,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  UserPlus,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, outreachApi, targetingApi } from '@/lib/api';
import type { QualityFlag, Suggestion, SuggestionAction } from '@/types';
import { Card, Chip, Button, EmptyState } from '@/components/ui';
import {
  bucketFlags,
  chipTone,
  readLength,
  SEVERITY_LABEL,
  SEVERITY_MEANING,
  sortFlags,
  worstSeverity,
  type FlagBucket,
} from '@/lib/guardrails';

// Action badges used to be four different ad-hoc colours (purple, sky,
// amber, slate). Collapsed to the two that actually matter for scanning:
// "this posts something" (accent) vs. passive engagement (neutral) — the
// tokens forced the question of which distinctions were worth keeping.
const ACTION_META: Record<
  SuggestionAction,
  { label: string; icon: typeof UserPlus; tone: 'accent' | 'neutral' }
> = {
  connect: { label: 'Connection request', icon: UserPlus, tone: 'accent' },
  message: { label: 'Direct message', icon: MessageSquare, tone: 'accent' },
  comment: { label: 'Comment on their post', icon: MessageSquare, tone: 'accent' },
  like: { label: 'Like their post', icon: Sparkles, tone: 'neutral' },
  follow: { label: 'Follow', icon: UserPlus, tone: 'neutral' },
};

// One approve/reject that's left the list visually but hasn't hit the API
// yet — the 5-second undo window. See scheduleAction() below.
interface PendingAction {
  key: string;
  suggestionId: string;
  name: string;
  kind: 'approve' | 'reject';
  editedText?: string;
  reason?: string;
  suppressTarget?: boolean;
  timer: ReturnType<typeof window.setTimeout>;
}

const UNDO_WINDOW_MS = 5000;

// The filter bar's two synthetic buckets, alongside the real rule codes.
const ALL = '__all__';
const CLEAN = '__clean__';

// The "why suggested" filter's catch-all bucket, alongside the real reason
// categories below.
const ALL_REASONS = '__all_reasons__';

// src/targeting/scoring.py writes one free-text sentence per matched
// criterion ("Title matches 'Head of Growth'", "Industry matches 'SaaS'"),
// each with a different value baked in — so there's no fixed small set of
// reasons to filter by directly. This groups them back into the five
// criteria the scorer actually checks, the same way GuardrailBar groups
// quality flags by rule instead of by exact sentence.
const REASON_CATEGORIES: { code: string; label: string; test: RegExp }[] = [
  { code: 'title', label: 'Title match', test: /^Title matches/i },
  { code: 'seniority', label: 'Seniority match', test: /^Seniority matches/i },
  { code: 'industry', label: 'Industry match', test: /^Industry matches/i },
  { code: 'keyword', label: 'Keyword match', test: /^Mentions/i },
  { code: 'location', label: 'Location match', test: /^Located in/i },
];

function categorizeReason(reason: string): { code: string; label: string } {
  const hit = REASON_CATEGORIES.find((c) => c.test.test(reason));
  return hit ?? { code: 'other', label: 'Other match' };
}

interface ReasonBucket {
  code: string;
  label: string;
  count: number;
}

// Counts suggestions, not reason occurrences — a person matched on both
// title and industry should count once toward each bucket, not twice toward
// one of them.
function bucketReasons(suggestions: Suggestion[]): ReasonBucket[] {
  const counts = new Map<string, ReasonBucket>();
  for (const s of suggestions) {
    const seen = new Set<string>();
    for (const reason of s.relevance_reasons ?? []) {
      const { code, label } = categorizeReason(reason);
      if (seen.has(code)) continue;
      seen.add(code);
      const existing = counts.get(code);
      if (existing) existing.count += 1;
      else counts.set(code, { code, label, count: 1 });
    }
  }
  return Array.from(counts.values()).sort((a, b) => b.count - a.count);
}

const SCORE_PRESETS = [0, 70, 85, 95];

// How the queue is ordered. "Best match" is the server's order (relevance
// first). "Failure type" groups every draft that broke the same rule
// together, which is the whole reason the filter exists: fourteen drafts
// with the same generic phrase are one decision, not fourteen.
type SortMode = 'match' | 'flag';

// One screenful at a time. The queue used to ask for 200 rows in one go and
// hope that covered it; at 400 pending, the rest were simply invisible.
const PAGE_SIZE = 50;

// The two lists an operator has. "Waiting" is the normal job. "Blocked" is
// copy the gate refused outright -- which until now was fetched by nothing and
// rendered nowhere, so a blocked draft just silently never appeared.
type QueueTab = 'pending' | 'blocked';

const ACCOUNT_TROUBLE: Record<string, { title: string; body: string; cta?: string }> = {
  auth_required: {
    title: 'This account is signed out of LinkedIn',
    body:
      "The saved session stopped working — usually LinkedIn expired it, or someone signed out. Nothing can be sent until it's reconnected, and anything approved will sit and wait.",
    cta: 'Reconnect it on the Accounts page',
  },
  rate_limited: {
    title: 'LinkedIn is rate-limiting this account',
    body:
      'LinkedIn pushed back on the last request. Sending is paused on purpose; pushing through a rate limit is how an account gets restricted. It usually clears on its own within a few hours.',
  },
  suspended: {
    title: 'This account is suspended',
    body: 'LinkedIn has restricted it. Nothing will send. This needs a human to look at the account itself before anything else here matters.',
    cta: 'Check it on the Accounts page',
  },
  error: {
    title: "Something is wrong with this account",
    body: 'The last thing we tried failed in a way we did not expect. Reviewing still works, but assume nothing will send until this clears.',
    cta: 'Check it on the Accounts page',
  },
  inactive: {
    title: 'This account is not active',
    body: "It's connected but switched off, so nothing will send. Approving still queues work for whenever it's turned back on.",
    cta: 'Check it on the Accounts page',
  },
};

export function Approvals() {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState<string>('');
  const [icpId, setIcpId] = useState<string>('');
  const [banner, setBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Keyboard-driven review: J/K move the selection, A approves, R opens the
  // reject-reason box. See the keydown effect below.
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Which of the two lists is open. Declared up here because the queue query
  // below is keyed on it.
  const [tab, setTab] = useState<QueueTab>('pending');
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Approve/reject write back through here rather than firing the instant
  // you click -- that's what lets Approve feel instant (nothing to wait on)
  // while still giving 5 real seconds to undo instead of a confirm dialog.
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [rejectDraft, setRejectDraft] = useState<{
    id: string;
    name: string;
    suppressTarget: boolean;
  } | null>(null);
  const [rejectReasonText, setRejectReasonText] = useState('');

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });
  const { data: icps = [] } = useQuery({
    queryKey: ['icps'],
    queryFn: targetingApi.listIcps,
  });

  // Default to the first active account once accounts load.
  useEffect(() => {
    if (!accountId && accounts.length) {
      setAccountId(accounts.find((a) => a.status === 'active')?.id ?? accounts[0].id);
    }
  }, [accounts, accountId]);

  const {
    data: pages,
    isLoading,
    isError: queueFailedToLoad,
    refetch: retryQueue,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['suggestions', accountId, tab],
    queryFn: ({ pageParam }) =>
      outreachApi.list(accountId || undefined, tab, { limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    // The server says whether there is more and where the next page starts;
    // computing it from the page length here would go wrong the moment
    // something is approved between two fetches.
    getNextPageParam: (last) =>
      last.has_more ? last.offset + last.suggestions.length : undefined,
    enabled: !!accountId,
  });

  const suggestions = useMemo(
    () => pages?.pages.flatMap((p) => p.suggestions) ?? [],
    [pages],
  );
  const queueTotal = pages?.pages[0]?.total ?? 0;

  // Counts for the other tab, so "Blocked 3" is visible without switching to
  // it. A blocked draft nobody knows about is the same as no draft at all.
  const { data: blockedCount = 0 } = useQuery({
    queryKey: ['suggestion-count', accountId, 'blocked'],
    queryFn: () => outreachApi.count(accountId || undefined, 'blocked'),
    enabled: !!accountId,
  });
  const { data: pendingCount = 0 } = useQuery({
    queryKey: ['suggestion-count', accountId, 'pending'],
    queryFn: () => outreachApi.count(accountId || undefined, 'pending'),
    enabled: !!accountId,
  });

  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Which failure type the operator is working through, and in what order.
  const [flagFilter, setFlagFilter] = useState<string>(ALL);
  const [sortMode, setSortMode] = useState<SortMode>('match');

  // Find-a-person / narrow-the-queue filters. Separate from flagFilter above
  // (that one is about what's wrong with the copy; these are about who the
  // suggestion is even for).
  const [searchQuery, setSearchQuery] = useState('');
  const [minScore, setMinScore] = useState(0);
  const [reasonFilter, setReasonFilter] = useState<string>(ALL_REASONS);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['suggestions'] });
    queryClient.invalidateQueries({ queryKey: ['suggestion-count'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  // Items with a pending action are hidden from the visible list the moment
  // you act on them -- that's the "instant" part. The real API call only
  // fires after the undo window, in commitPending below.
  const pendingIds = useMemo(() => new Set(pending.map((p) => p.suggestionId)), [pending]);
  const visibleSuggestions = useMemo(
    () => suggestions.filter((s) => !pendingIds.has(s.id)),
    [suggestions, pendingIds],
  );

  // Counted over everything still visible, not over the filtered view --
  // otherwise picking "Too long" would collapse every other count to zero
  // and there'd be no way back without clearing the filter first.
  const buckets = useMemo(() => bucketFlags(visibleSuggestions), [visibleSuggestions]);
  const cleanCount = useMemo(
    () => visibleSuggestions.filter((s) => !(s.quality_flags ?? []).length).length,
    [visibleSuggestions],
  );

  // A filter that would show nothing is a dead end -- if the last item with
  // this failure type just got approved, fall back to the whole queue rather
  // than leaving the operator staring at an empty list.
  useEffect(() => {
    if (flagFilter === ALL) return;
    if (flagFilter === CLEAN ? cleanCount === 0 : !buckets.some((b) => b.code === flagFilter)) {
      setFlagFilter(ALL);
    }
  }, [buckets, cleanCount, flagFilter]);

  // Same dead-end guard as flagFilter above, for the "why suggested" pills.
  const reasonBuckets = useMemo(() => bucketReasons(visibleSuggestions), [visibleSuggestions]);
  useEffect(() => {
    if (reasonFilter === ALL_REASONS) return;
    if (!reasonBuckets.some((b) => b.code === reasonFilter)) setReasonFilter(ALL_REASONS);
  }, [reasonBuckets, reasonFilter]);

  const listed = useMemo(() => {
    let rows = visibleSuggestions;
    if (flagFilter === CLEAN) {
      rows = rows.filter((s) => !(s.quality_flags ?? []).length);
    } else if (flagFilter !== ALL) {
      rows = rows.filter((s) => (s.quality_flags ?? []).some((f) => f.code === flagFilter));
    }
    if (reasonFilter !== ALL_REASONS) {
      rows = rows.filter((s) =>
        (s.relevance_reasons ?? []).some((r) => categorizeReason(r).code === reasonFilter),
      );
    }
    if (minScore > 0) {
      rows = rows.filter((s) => s.relevance_score >= minScore);
    }
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      rows = rows.filter((s) => {
        const t = s.target;
        const haystack = [
          t?.full_name,
          t?.title,
          t?.company,
          t?.headline,
          s.draft_text,
          s.final_text,
          ...(s.relevance_reasons ?? []),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(q);
      });
    }
    if (sortMode === 'flag') {
      // Worst severity first, then all of one rule together, then best match
      // within the group. Clean drafts sort last: nothing to batch there.
      rows = [...rows].sort((a, b) => {
        const sa = worstSeverity(a.quality_flags);
        const sb = worstSeverity(b.quality_flags);
        if (sa !== sb) return sa - sb;
        const ca = sortFlags(a.quality_flags ?? [])[0]?.code ?? '';
        const cb = sortFlags(b.quality_flags ?? [])[0]?.code ?? '';
        if (ca !== cb) return ca.localeCompare(cb);
        return b.relevance_score - a.relevance_score;
      });
    }
    return rows;
  }, [visibleSuggestions, flagFilter, reasonFilter, minScore, searchQuery, sortMode]);

  // Clamp selection when the list shrinks (an action fires, a filter narrows
  // it) or grows (an undo brings something back).
  useEffect(() => {
    setSelectedIndex((i) => Math.min(i, Math.max(0, listed.length - 1)));
  }, [listed.length]);

  useEffect(() => {
    const current = listed[selectedIndex];
    if (current) rowRefs.current[current.id]?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex, listed]);

  const commitPending = async (action: PendingAction) => {
    try {
      if (action.kind === 'approve') {
        await outreachApi.approve(action.suggestionId, action.editedText);
      } else {
        await outreachApi.reject(action.suggestionId, action.reason ?? '', action.suppressTarget ?? false);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? `Could not ${action.kind} ${action.name}`);
    } finally {
      // Cleared whether it succeeded or failed. A failure just means the
      // item reappears in the list (it was never actually removed from the
      // query cache, only hidden) -- the error banner explains why.
      setPending((p) => p.filter((x) => x.key !== action.key));
      invalidate();
    }
  };

  const scheduleAction = (
    suggestion: Suggestion,
    kind: 'approve' | 'reject',
    extra?: { editedText?: string; reason?: string; suppressTarget?: boolean },
  ) => {
    const key = `${kind}-${suggestion.id}-${Date.now()}`;
    const action: PendingAction = {
      key,
      suggestionId: suggestion.id,
      name: suggestion.target?.full_name ?? 'this person',
      kind,
      ...extra,
      timer: window.setTimeout(() => commitPending(action), UNDO_WINDOW_MS),
    };
    setPending((p) => [...p, action]);
    if (expandedId === suggestion.id) setExpandedId(null);
  };

  const undoPending = (key: string) => {
    setPending((p) => {
      const found = p.find((x) => x.key === key);
      if (found) window.clearTimeout(found.timer);
      return p.filter((x) => x.key !== key);
    });
  };

  const openRejectPrompt = (suggestion: Suggestion, suppressTarget: boolean) => {
    setRejectReasonText('');
    setRejectDraft({
      id: suggestion.id,
      name: suggestion.target?.full_name ?? 'this person',
      suppressTarget,
    });
  };

  const submitRejectPrompt = () => {
    if (!rejectDraft || !rejectReasonText.trim()) return;
    const suggestion = suggestions.find((s) => s.id === rejectDraft.id);
    if (suggestion) {
      scheduleAction(suggestion, 'reject', {
        reason: rejectReasonText.trim(),
        suppressTarget: rejectDraft.suppressTarget,
      });
    }
    setRejectDraft(null);
    setRejectReasonText('');
  };

  // J/K/A/R only act when nobody is typing anywhere else on the page --
  // otherwise "reject reason" text or an in-progress edit would get eaten
  // by the shortcuts meant for the list.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? '').toLowerCase();
      const typing = tag === 'input' || tag === 'textarea' || tag === 'select';
      if (typing || expandedId || rejectDraft || listed.length === 0) return;

      if (e.key === 'j' || e.key === 'J') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, listed.length - 1));
      } else if (e.key === 'k' || e.key === 'K') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'a' || e.key === 'A') {
        e.preventDefault();
        const s = listed[selectedIndex];
        if (s) scheduleAction(s, 'approve');
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        const s = listed[selectedIndex];
        if (s) openRejectPrompt(s, false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [listed, selectedIndex, expandedId, rejectDraft]);

  const generate = useMutation({
    mutationFn: () => outreachApi.generate(accountId, icpId || undefined),
    onSuccess: (result) => {
      setError(null);
      setBanner(result.message);
      invalidate();
    },
    onError: (err: any) => setError(err?.response?.data?.detail ?? 'Could not generate suggestions'),
  });

  const activeAccount = useMemo(
    () => accounts.find((a) => a.id === accountId),
    [accounts, accountId],
  );

  if (!accounts.length) {
    return (
      <EmptyState
        icon={<Send size={40} />}
        title="Connect an account first"
        body="The approval queue shows outreach proposed on behalf of a connected LinkedIn account. Add one to get started."
        cta={{ label: 'Go to Accounts', href: '/accounts' }}
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Approvals</h1>
        <p className="text-slate-400 mt-1">
          Nothing is sent to LinkedIn until you approve it here.
        </p>
      </header>

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3 mb-6 p-4 rounded-xl bg-slate-800/60 border border-slate-700">
        <Field label="Account">
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="select"
          >
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name ?? 'Unnamed account'}
                {account.status !== 'active' ? ` (${account.status})` : ''}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Target profile">
          <select value={icpId} onChange={(e) => setIcpId(e.target.value)} className="select">
            <option value="">Account default</option>
            {icps.map((icp) => (
              <option key={icp.id} value={icp.id}>
                {icp.name}
              </option>
            ))}
          </select>
        </Field>

        <button
          onClick={() => generate.mutate()}
          disabled={generate.isPending || !accountId}
          className="btn-primary"
        >
          {generate.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Sparkles size={16} />
          )}
          Suggest who to contact
        </button>

        {activeAccount && (
          <div className="ml-auto text-xs text-slate-400 text-right leading-relaxed">
            <div>
              Up to{' '}
              <span className="text-slate-200 font-medium">
                {activeAccount.policy?.actions?.connect?.per_day ?? '—'}
              </span>{' '}
              invitations/day
            </div>
            <div>
              Active {activeAccount.policy?.active_hours?.[0]}:00–
              {activeAccount.policy?.active_hours?.[1]}:00
              {activeAccount.policy?.warmup ? ' · warming up' : ''}
            </div>
          </div>
        )}
      </div>

      {/* A dropped connection is not a queue problem, so it does not belong in
          the queue's error state -- reviewing still works, sending does not.
          Said once, at the top, in the words of what actually happens. */}
      {activeAccount && ACCOUNT_TROUBLE[activeAccount.status] && (
        <AccountTrouble status={activeAccount.status} name={activeAccount.display_name} />
      )}

      {banner && (
        <Notice tone="info" onDismiss={() => setBanner(null)}>
          {banner}
        </Notice>
      )}
      {error && (
        <Notice tone="error" onDismiss={() => setError(null)}>
          {error}
        </Notice>
      )}

      {isLoading ? (
        // Loading: a real state, not "empty until proven otherwise". A slow
        // network shouldn't look identical to a genuinely empty queue.
        <div className="flex flex-col items-center gap-3 py-16 text-muted">
          <Loader2 className="animate-spin" size={22} />
          <span className="text-sm">Loading the queue…</span>
        </div>
      ) : queueFailedToLoad ? (
        // Error: distinct from empty. A failed fetch used to fall through
        // to suggestions=[] and silently render "Nothing waiting for
        // review" — indistinguishable from a real empty queue. Fixed
        // 2026-09-01.
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <AlertTriangle className="text-danger" size={32} />
          <div>
            <p className="text-foreground font-medium">Couldn't load the queue</p>
            <p className="text-muted text-sm mt-1">The suggestions list didn't come back. Your connection, or the server, might be down.</p>
          </div>
          <Button variant="ghost" onClick={() => retryQueue()}>Try again</Button>
        </div>
      ) : suggestions.length === 0 ? (
        <>
          <QueueTabs
            tab={tab}
            pendingCount={pendingCount}
            blockedCount={blockedCount}
            onChange={(next) => { setTab(next); setSelectedIndex(0); setExpandedId(null); }}
          />
          {tab === 'blocked' ? (
            <EmptyState
              icon={<ShieldCheck size={40} />}
              title="Nothing was blocked"
              body="Drafts land here when the quality gate refuses them outright — a leaked merge field, a booking link, copy over the length limit. An empty list is the good outcome."
            />
          ) : (
            <EmptyState
              icon={<Send size={40} />}
              title="Nothing waiting for review"
              body="Import some people on the Targeting page, then use “Suggest who to contact”. Only strong matches make it this far."
            />
          )}
        </>
      ) : (
        <>
          <QueueTabs
            tab={tab}
            pendingCount={pendingCount}
            blockedCount={blockedCount}
            onChange={(next) => { setTab(next); setSelectedIndex(0); setExpandedId(null); }}
          />

          {tab === 'blocked' && (
            <p className="text-xs text-muted mb-3 flex items-start gap-1.5">
              <AlertTriangle size={13} className="text-danger-fg shrink-0 mt-0.5" />
              <span>
                These were refused by the quality gate, not by a person. Edit the copy to fix what
                it objected to and approve it, or skip it — approving re-runs the same check, so a
                blocked draft cannot slip through unedited.
              </span>
            </p>
          )}

          <SuggestionFilterBar
            search={searchQuery}
            onSearch={(value) => { setSearchQuery(value); setSelectedIndex(0); }}
            minScore={minScore}
            onMinScore={(value) => { setMinScore(value); setSelectedIndex(0); }}
            reasonBuckets={reasonBuckets}
            reasonFilter={reasonFilter}
            onReasonFilter={(code) => { setReasonFilter(code); setSelectedIndex(0); }}
            totalForReasons={visibleSuggestions.length}
          />

          <GuardrailBar
            buckets={buckets}
            total={visibleSuggestions.length}
            cleanCount={cleanCount}
            active={flagFilter}
            onFilter={(code) => {
              setFlagFilter(code);
              setSelectedIndex(0);
            }}
            sortMode={sortMode}
            onSort={setSortMode}
          />

          {listed.length === 0 && (
            <div className="mb-3 rounded-lg border border-dashed border-border px-4 py-6 text-center">
              <p className="text-sm text-muted">
                Nothing in the queue matches these filters.
              </p>
              <button
                onClick={() => {
                  setSearchQuery('');
                  setMinScore(0);
                  setReasonFilter(ALL_REASONS);
                  setFlagFilter(ALL);
                }}
                className="text-sm text-accent hover:underline mt-1"
              >
                Clear filters
              </button>
            </div>
          )}

          <p className="text-xs text-muted mb-2">
            <kbd className="px-1 py-0.5 rounded bg-slate-800 border border-slate-600">J</kbd>{' '}
            <kbd className="px-1 py-0.5 rounded bg-slate-800 border border-slate-600">K</kbd> to move ·{' '}
            <kbd className="px-1 py-0.5 rounded bg-slate-800 border border-slate-600">A</kbd> approve ·{' '}
            <kbd className="px-1 py-0.5 rounded bg-slate-800 border border-slate-600">R</kbd> reject
          </p>
          <div className="flex flex-col gap-2">
            {listed.map((suggestion, index) =>
              expandedId === suggestion.id ? (
                <SuggestionCard
                  key={suggestion.id}
                  suggestion={suggestion}
                  onApprove={(editedText) => scheduleAction(suggestion, 'approve', { editedText })}
                  onReject={(suppressTarget) => openRejectPrompt(suggestion, suppressTarget)}
                  onCollapse={() => setExpandedId(null)}
                />
              ) : (
                <QueueRow
                  key={suggestion.id}
                  rowRef={(el) => { rowRefs.current[suggestion.id] = el; }}
                  suggestion={suggestion}
                  selected={index === selectedIndex}
                  onSelect={() => setSelectedIndex(index)}
                  onExpand={() => {
                    setSelectedIndex(index);
                    setExpandedId(suggestion.id);
                  }}
                  onApprove={() => scheduleAction(suggestion, 'approve')}
                  onReject={() => openRejectPrompt(suggestion, false)}
                />
              ),
            )}
          </div>

          {/* How much of the queue you are actually looking at. The old screen
              asked for 200 rows and said nothing when there were more. */}
          <div className="mt-4 flex flex-col items-center gap-2">
            <p className="text-xs text-muted">
              Showing {listed.length}
              {listed.length !== suggestions.length ? ` of ${suggestions.length} loaded` : ''}
              {queueTotal > suggestions.length ? ` · ${queueTotal} in the queue` : ''}
            </p>
            {hasNextPage && (
              <Button
                variant="ghost"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                icon={isFetchingNextPage ? <Loader2 size={14} className="animate-spin" /> : undefined}
              >
                {isFetchingNextPage
                  ? 'Loading…'
                  : `Load ${Math.min(PAGE_SIZE, queueTotal - suggestions.length)} more`}
              </Button>
            )}
          </div>
        </>
      )}

      {/* Reject needs a reason -- it's the data that improves the prompt
          later, not a courtesy. Typed, not a browser confirm(); confirms
          are what people learn to click through without reading. */}
      {rejectDraft && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 w-full max-w-lg px-4">
          {/* Stacked on a phone: at 390px the label, the input and the button
              side by side left the input about 40px wide. */}
          <div className="rounded-lg border border-danger/60 bg-slate-900 shadow-xl p-3 flex flex-col sm:flex-row sm:items-center gap-2">
            <span className="text-sm text-foreground sm:shrink-0">
              Why skip {rejectDraft.name}
              {rejectDraft.suppressTarget ? ' — and never contact again' : ''}?
            </span>
            <input
              autoFocus
              value={rejectReasonText}
              onChange={(e) => setRejectReasonText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  submitRejectPrompt();
                } else if (e.key === 'Escape') {
                  e.preventDefault();
                  setRejectDraft(null);
                  setRejectReasonText('');
                }
              }}
              placeholder="Reason, then Enter"
              className="flex-1 min-w-0 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent"
            />
            <Button
              variant="danger"
              disabled={!rejectReasonText.trim()}
              onClick={submitRejectPrompt}
              className="px-2.5 py-1 text-xs shrink-0"
            >
              Reject
            </Button>
          </div>
        </div>
      )}

      {/* The 5-second undo. Nothing here has hit the API yet -- that only
          happens in commitPending, once (if) this timer runs out. */}
      {pending.length > 0 && (
        <div className="fixed bottom-4 right-4 z-30 flex flex-col gap-2">
          {pending.map((p) => (
            <div
              key={p.key}
              className="flex items-center gap-3 rounded-lg border border-border bg-slate-900 shadow-xl px-3 py-2 text-sm"
            >
              <span className="text-foreground">
                {p.kind === 'approve' ? 'Approved' : 'Skipped'} {p.name}
              </span>
              <button
                onClick={() => undoPending(p.key)}
                className="text-accent font-medium hover:underline shrink-0"
              >
                Undo
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// The compact row: what the queue looks like by default. Scanning many
// items is the actual job here, so the draft and the source post are both
// clamped to a couple of lines each — a 900-character comment must not be
// able to stretch a row into a wall of text. Click a row to expand it into
// the full card below (edit, confirm-guarded Never Contact, everything).
function QueueRow({
  suggestion,
  selected,
  onSelect,
  onExpand,
  onApprove,
  onReject,
  rowRef,
}: {
  suggestion: Suggestion;
  selected: boolean;
  onSelect: () => void;
  onExpand: () => void;
  onApprove: () => void;
  onReject: () => void;
  rowRef: (el: HTMLDivElement | null) => void;
}) {
  const meta = ACTION_META[suggestion.action] ?? ACTION_META.connect;
  const Icon = meta.icon;
  const target = suggestion.target;
  const text = suggestion.final_text ?? suggestion.draft_text ?? '';
  const flags = sortFlags(suggestion.quality_flags ?? []);
  const blocked = flags.some((f) => f.severity === 'blocker');

  return (
    <div
      ref={rowRef}
      className={clsx('rounded-lg transition-shadow', selected && 'ring-2 ring-accent')}
    >
    <Card padded={false} className="overflow-hidden">
      {/* Side by side on a laptop, stacked on a phone.
          Three fixed-width columns in a 390px viewport left the comment
          itself about 150px to live in — two clipped lines of the one thing
          the row exists to show, with the source post underneath it reduced
          to "Replying to: We cut our :". On a narrow screen the name and the
          score share one line and everything else gets the full width. */}
      <button
        onClick={() => { onSelect(); onExpand(); }}
        onMouseEnter={onSelect}
        className="w-full text-left p-3 flex items-start gap-3 hover:bg-surface/80 transition-colors"
      >
        <ChevronRight size={16} className="hidden sm:block text-muted shrink-0 mt-1.5" />

        <div className="flex-1 min-w-0 flex flex-col gap-2 sm:flex-row sm:gap-3 sm:items-start">
          <div className="flex items-start justify-between gap-2 sm:block sm:w-40 sm:shrink-0">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-foreground truncate">{target?.full_name ?? 'Unknown person'}</div>
              <div className="text-xs text-muted truncate">{target?.title ?? target?.headline ?? ''}</div>
            </div>
            <div className="sm:hidden shrink-0 text-right">
              <span className="text-sm font-semibold text-foreground">{suggestion.relevance_score}</span>
              <span className="text-[10px] uppercase text-muted ml-1">match</span>
            </div>
          </div>

          <div className="flex-1 min-w-0 flex flex-col gap-1">
            <div className="flex items-center gap-2 flex-wrap">
              <Chip tone={meta.tone} icon={<Icon size={10} />} className="shrink-0">{meta.label}</Chip>
              {/* Why this one was flagged, right here in the row. Before this
                  you had to open a card to find out, which is exactly the
                  thing that makes a reviewer ask someone what the rule was. */}
              <FlagChips flags={flags} limit={3} size="row" />
            </div>
            <p className="text-sm text-slate-200 line-clamp-2">{text || <span className="text-muted">No draft</span>}</p>
            {target?.post_text && (
              <p className="text-xs text-muted flex items-start gap-1">
                <Quote size={11} className="shrink-0 mt-0.5" />
                <span className="truncate">Replying to: {target.post_text}</span>
              </p>
            )}
          </div>

          <div className="hidden sm:block shrink-0 text-center w-12">
            <div className="text-sm font-semibold text-foreground">{suggestion.relevance_score}</div>
            <div className="text-[10px] uppercase text-muted">match</div>
          </div>
        </div>
      </button>

      <div className="px-3 pb-3 sm:pl-9 flex items-center gap-2">
        {/* A draft carrying a blocker cannot be approved as it stands -- the
            gate re-checks on approve and refuses. Letting the button fire
            anyway costs the operator the full undo window to be told what the
            chip beside it already says, so the row sends them to the editor
            instead. The expanded card's Approve stays live: that is where the
            text can actually be fixed. */}
        <Button
          variant="success"
          onClick={(e) => { e.stopPropagation(); blocked ? onExpand() : onApprove(); }}
          icon={<Check size={13} />}
          className="px-2.5 py-1 text-xs"
          disabled={blocked}
          title={blocked ? 'Blocked by the quality gate — open it and fix the copy first' : undefined}
        >
          Approve
        </Button>
        <Button
          variant="ghost"
          onClick={(e) => { e.stopPropagation(); onReject(); }}
          icon={<X size={13} />}
          className="px-2.5 py-1 text-xs"
        >
          Skip
        </Button>
        <Button variant="ghost" onClick={onExpand} className="px-2.5 py-1 text-xs ml-auto">
          Open <ChevronDown size={13} />
        </Button>
      </div>
    </Card>
    </div>
  );
}

function SuggestionCard({
  suggestion,
  onApprove,
  onReject,
  onCollapse,
}: {
  suggestion: Suggestion;
  onApprove: (editedText?: string) => void;
  onReject: (suppressTarget: boolean) => void;
  onCollapse?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [text, setText] = useState(suggestion.final_text ?? suggestion.draft_text ?? '');
  const meta = ACTION_META[suggestion.action] ?? ACTION_META.connect;
  const Icon = meta.icon;
  const target = suggestion.target;

  // Recomputed on every keystroke while editing -- the point is to stop a
  // comment going over before it is submitted, not to reject it afterwards.
  const reading = readLength(text, suggestion.action);
  const overLimit = reading.overHardLimit;
  const flags = sortFlags(suggestion.quality_flags ?? []);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <Card padded={false} className="overflow-hidden">
      {onCollapse && (
        <button
          onClick={onCollapse}
          className="w-full text-left px-5 py-2 text-xs text-muted hover:text-foreground border-b border-border flex items-center gap-1"
        >
          <ChevronDown size={13} className="rotate-90" /> Back to list
        </button>
      )}
      {/* Who */}
      <div className="p-4 sm:p-5 pb-3 flex items-start gap-3 sm:gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-foreground font-semibold truncate">
              {target?.full_name ?? 'Unknown person'}
            </h3>
            {target?.profile_url && (
              <a
                href={target.profile_url}
                target="_blank"
                rel="noreferrer"
                className="text-muted hover:text-foreground"
                title="Open LinkedIn profile"
              >
                <ExternalLink size={14} />
              </a>
            )}
            <Chip tone={meta.tone} icon={<Icon size={11} />}>
              {meta.label}
            </Chip>
          </div>
          {target?.headline && (
            <p className="text-sm text-muted mt-0.5 truncate">{target.headline}</p>
          )}
        </div>

        <RelevanceBadge score={suggestion.relevance_score} />
      </div>

      {/* What they posted — an operator can't judge a reply without seeing
          what it's replying to. Missing from the API entirely until
          2026-09-01. */}
      {target?.post_text && (
        <div className="px-5 pb-3">
          <div className="flex items-start gap-2 text-sm text-muted bg-surface/80 rounded-lg p-3">
            <Quote size={14} className="shrink-0 mt-0.5 text-muted" />
            <span className="whitespace-pre-wrap">{target.post_text}</span>
          </div>
        </div>
      )}

      {/* Why them */}
      {suggestion.relevance_reasons.length > 0 && (
        <div className="px-5 pb-3 flex flex-wrap gap-1.5">
          {suggestion.relevance_reasons.map((reason) => (
            <Chip key={reason} tone="neutral">
              {reason}
            </Chip>
          ))}
        </div>
      )}

      {/* What we'd say */}
      <div className="px-5 pb-4">
        {editing ? (
          <div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              className="w-full rounded-lg bg-slate-900 border border-slate-600 text-slate-100 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            />
            {/* The live counter. Amber before the wall, red at it. Three
                states rather than two, because "you have 20 characters
                left" and "this can't be sent" are different problems and
                only one of them is still fixable. */}
            <div
              className={clsx(
                'text-xs mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 transition-colors',
                reading.tone === 'danger' && 'text-danger-fg',
                reading.tone === 'warn' && 'text-warn',
                reading.tone === 'muted' && 'text-muted',
              )}
              aria-live="polite"
            >
              <span className="tabular-nums font-medium">
                {reading.chars}
                {reading.hardLimit ? ` / ${reading.hardLimit}` : ''} characters
              </span>
              {suggestion.action === 'comment' && (
                <span className="tabular-nums">
                  · {reading.sentences} {reading.sentences === 1 ? 'sentence' : 'sentences'}
                </span>
              )}
              {reading.note && <span>· {reading.note}</span>}
            </div>
          </div>
        ) : (
          <blockquote className="rounded-lg bg-slate-900/70 border-l-2 border-accent p-3 text-sm text-slate-200 whitespace-pre-wrap">
            {text || <span className="text-muted">No draft</span>}
          </blockquote>
        )}

        {/* Honesty: how the copy was made and what's weak about it */}
        <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-muted">
          {suggestion.generated_by && <span>Written by {suggestion.generated_by}</span>}
          {typeof suggestion.quality_score === 'number' && (
            <span>Quality {suggestion.quality_score}/100</span>
          )}
        </div>

        {/* Every rule this draft broke, named, with what it means and what
            the copy actually did. One vocabulary: the same words appear on
            the compact row, in the filter bar, and in the spec. Includes
            the cross-queue repetition check -- the thing a one-at-a-time
            review can never show on its own (src/outreach/similarity.py). */}
        {flags.length > 0 ? (
          <div className="mt-3 flex flex-col gap-1.5">
            {flags.map((flag) => (
              <div key={flag.code + flag.detail} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <Chip
                  tone={chipTone(flag.severity)}
                  icon={<AlertTriangle size={11} />}
                  className="shrink-0"
                >
                  {flag.label}
                </Chip>
                <span className="text-xs text-muted">{flag.detail}</span>
                <span className="text-[10px] uppercase tracking-wide text-muted/70">
                  {SEVERITY_LABEL[flag.severity]}
                  {flag.spec_ref ? ` · ${flag.spec_ref}` : ' · not in the spec yet'}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-1.5 text-xs text-success-fg">
            <ShieldCheck size={13} /> Passed every rule we check
          </div>
        )}
      </div>

      {/* Decide */}
      <div className="px-5 py-3 bg-slate-900/40 border-t border-border flex flex-wrap items-center gap-2">
        <Button
          variant="success"
          onClick={() => onApprove(editing ? text : undefined)}
          disabled={overLimit || !text.trim()}
          icon={<Check size={15} />}
        >
          Approve{editing ? ' edit' : ''} &amp; schedule
        </Button>

        <Button variant="ghost" onClick={() => setEditing((v) => !v)} icon={<Pencil size={15} />}>
          {editing ? 'Cancel edit' : 'Edit'}
        </Button>

        <Button variant="ghost" onClick={() => onReject(false)} icon={<X size={15} />}>
          Skip
        </Button>

        {/* Permanent action, two taps: click asks, a second click starts the
            reject-reason prompt. Set apart by distance, weight, and a real
            confirm step — not colour alone. */}
        {confirmingReject ? (
          <div className="ml-auto flex items-center gap-2 rounded-md border border-danger/60 bg-danger/10 px-3 py-1.5">
            <span className="text-sm text-foreground">
              Never contact {target?.full_name ?? 'this person'}?
            </span>
            <Button
              variant="danger"
              onClick={() => onReject(true)}
              icon={<Ban size={14} />}
              className="px-3 py-1.5"
            >
              Confirm
            </Button>
            <Button
              variant="ghost"
              onClick={() => setConfirmingReject(false)}
              className="px-3 py-1.5"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="danger"
            onClick={() => setConfirmingReject(true)}
            icon={<Ban size={15} />}
            className="ml-auto"
            title="Never contact this person again"
          >
            Never contact
          </Button>
        )}
      </div>
      </Card>
    </motion.div>
  );
}

/**
 * Find-a-person filters: search text, a minimum match score, and which of
 * the scorer's own criteria (title, seniority, industry, keyword, location)
 * the suggestion was matched on. Separate from GuardrailBar below, which
 * filters by what's wrong with the copy rather than who it's for.
 */
function SuggestionFilterBar({
  search,
  onSearch,
  minScore,
  onMinScore,
  reasonBuckets,
  reasonFilter,
  onReasonFilter,
  totalForReasons,
}: {
  search: string;
  onSearch: (value: string) => void;
  minScore: number;
  onMinScore: (value: number) => void;
  reasonBuckets: ReasonBucket[];
  reasonFilter: string;
  onReasonFilter: (code: string) => void;
  totalForReasons: number;
}) {
  return (
    <div className="mb-3 rounded-lg border border-border bg-surface/40 p-3 flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="relative">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search name, title, company…"
          className="pl-7 pr-2 py-1.5 text-xs rounded-md bg-slate-900 border border-slate-600 text-slate-100 w-52 focus:outline-none focus:ring-2 focus:ring-accent placeholder:text-muted"
        />
      </div>

      <label className="flex items-center gap-1.5 text-xs text-muted">
        Match score
        <select
          value={minScore}
          onChange={(e) => onMinScore(Number(e.target.value))}
          className="select py-1 text-xs"
        >
          {SCORE_PRESETS.map((preset) => (
            <option key={preset} value={preset}>
              {preset === 0 ? 'Any' : `${preset}+`}
            </option>
          ))}
        </select>
      </label>

      {reasonBuckets.length > 0 && (
        <>
          <span className="text-xs text-muted shrink-0">Why suggested</span>
          <FilterPill
            label="Everything"
            count={totalForReasons}
            tone="neutral"
            active={reasonFilter === ALL_REASONS}
            onClick={() => onReasonFilter(ALL_REASONS)}
          />
          {reasonBuckets.map((bucket) => (
            <FilterPill
              key={bucket.code}
              label={bucket.label}
              count={bucket.count}
              tone="neutral"
              active={reasonFilter === bucket.code}
              onClick={() => onReasonFilter(bucket.code)}
            />
          ))}
        </>
      )}
    </div>
  );
}

/**
 * The failure-type filter, above the list.
 *
 * The counts are the useful part. "Generic phrase 14" tells an operator
 * where the queue's real problem is before they have read a single draft,
 * and clicking it turns fourteen separate judgement calls into one pass
 * through fourteen instances of the same mistake.
 */
function GuardrailBar({
  buckets,
  total,
  cleanCount,
  active,
  onFilter,
  sortMode,
  onSort,
}: {
  buckets: FlagBucket[];
  total: number;
  cleanCount: number;
  active: string;
  onFilter: (code: string) => void;
  sortMode: SortMode;
  onSort: (mode: SortMode) => void;
}) {
  if (!buckets.length && cleanCount === total) {
    return (
      <div className="mb-3 flex items-center gap-1.5 text-xs text-success-fg">
        <ShieldCheck size={14} /> Nothing in this queue breaks a rule.
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-border bg-surface/40 p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-xs text-muted shrink-0">Flagged</span>

        <FilterPill
          label="Everything"
          count={total}
          tone="neutral"
          active={active === ALL}
          onClick={() => onFilter(ALL)}
        />

        {buckets.map((bucket) => (
          <FilterPill
            key={bucket.code}
            label={bucket.label}
            count={bucket.count}
            tone={chipTone(bucket.severity)}
            active={active === bucket.code}
            onClick={() => onFilter(bucket.code)}
            title={`${bucket.code} · ${SEVERITY_MEANING[bucket.severity]}${
              bucket.specRef ? ` · ${bucket.specRef}` : ' · not in the spec yet'
            }`}
          />
        ))}

        {cleanCount > 0 && (
          <FilterPill
            label="Nothing flagged"
            count={cleanCount}
            tone="success"
            active={active === CLEAN}
            onClick={() => onFilter(CLEAN)}
          />
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-xs text-muted">Sort</span>
          <SortToggle label="Best match" active={sortMode === 'match'} onClick={() => onSort('match')} />
          <SortToggle
            label="Failure type"
            active={sortMode === 'flag'}
            onClick={() => onSort('flag')}
            title="Group every draft that broke the same rule together"
          />
        </div>
      </div>
    </div>
  );
}

function FilterPill({
  label,
  count,
  tone,
  active,
  onClick,
  title,
}: {
  label: string;
  count: number;
  tone: 'danger' | 'warn' | 'neutral' | 'success';
  active: boolean;
  onClick: () => void;
  title?: string;
}) {
  // Selection is a ring plus a filled count, never colour alone -- the tone
  // already means severity here, so it can't also mean "selected".
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={title}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full pl-2.5 pr-1.5 py-0.5 text-xs font-medium',
        'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        active ? 'ring-2 ring-accent' : 'hover:brightness-125',
        tone === 'danger' && 'bg-danger/15 text-danger-fg',
        tone === 'warn' && 'bg-warn/15 text-warn',
        tone === 'success' && 'bg-success/15 text-success-fg',
        tone === 'neutral' && 'bg-surface text-muted',
      )}
    >
      {label}
      <span className="rounded-full bg-black/25 px-1.5 tabular-nums">{count}</span>
    </button>
  );
}

function SortToggle({
  label,
  active,
  onClick,
  title,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={title}
      className={clsx(
        'rounded-md px-2 py-0.5 text-xs font-medium transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        active ? 'bg-accent/15 text-accent' : 'text-muted hover:text-foreground',
      )}
    >
      {label}
    </button>
  );
}

/** The flag chips on a compact row: worst first, capped so one badly broken
 *  draft can't push the person's name off the screen. */
function FlagChips({
  flags,
  limit,
  size,
}: {
  flags: QualityFlag[];
  limit: number;
  size: 'row' | 'card';
}) {
  if (!flags.length) return null;
  const shown = flags.slice(0, limit);
  const hidden = flags.length - shown.length;
  const icon = size === 'row' ? 10 : 11;
  return (
    <>
      {shown.map((flag) => (
        <Chip
          key={flag.code + flag.detail}
          tone={chipTone(flag.severity)}
          icon={<AlertTriangle size={icon} />}
          className="shrink-0"
          // Hover gives the specifics without spending row height on them.
        >
          <span title={`${flag.detail} — ${SEVERITY_MEANING[flag.severity]}`}>{flag.label}</span>
        </Chip>
      ))}
      {hidden > 0 && (
        <Chip tone="neutral" className="shrink-0">
          +{hidden} more
        </Chip>
      )}
    </>
  );
}

/** Waiting vs blocked. Blocked drafts existed in the database from day one
 *  and were fetched by nothing, so nobody could see the gate had refused
 *  anything — the queue simply looked shorter. */
function QueueTabs({
  tab,
  pendingCount,
  blockedCount,
  onChange,
}: {
  tab: QueueTab;
  pendingCount: number;
  blockedCount: number;
  onChange: (tab: QueueTab) => void;
}) {
  return (
    <div className="flex items-center gap-1 mb-3 border-b border-border">
      <TabButton
        label="Waiting for review"
        count={pendingCount}
        active={tab === 'pending'}
        onClick={() => onChange('pending')}
      />
      <TabButton
        label="Blocked by the gate"
        count={blockedCount}
        tone={blockedCount > 0 ? 'danger' : 'muted'}
        active={tab === 'blocked'}
        onClick={() => onChange('blocked')}
      />
    </div>
  );
}

function TabButton({
  label,
  count,
  active,
  onClick,
  tone = 'muted',
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  tone?: 'muted' | 'danger';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        'relative px-2.5 sm:px-3 py-2 text-xs sm:text-sm font-medium whitespace-nowrap',
        'transition-colors -mb-px border-b-2',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t',
        active
          ? 'text-foreground border-accent'
          : 'text-muted border-transparent hover:text-foreground',
      )}
    >
      {label}
      <span
        className={clsx(
          'ml-2 rounded-full px-1.5 py-0.5 text-xs tabular-nums',
          tone === 'danger' && count > 0 ? 'bg-danger/15 text-danger-fg' : 'bg-surface text-muted',
        )}
      >
        {count}
      </span>
    </button>
  );
}

/** The account itself is in trouble. Reviewing still works; sending does not. */
function AccountTrouble({ status, name }: { status: string; name?: string }) {
  const copy = ACCOUNT_TROUBLE[status];
  if (!copy) return null;
  return (
    <div className="mb-4 rounded-lg border border-warn/50 bg-warn/10 px-4 py-3 flex items-start gap-3">
      <PlugZap size={18} className="text-warn shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">
          {copy.title}
          {name ? ` — ${name}` : ''}
        </p>
        <p className="text-sm text-muted mt-0.5">{copy.body}</p>
        {copy.cta && (
          <a href="/accounts" className="text-sm text-accent hover:underline mt-1 inline-block">
            {copy.cta} →
          </a>
        )}
      </div>
    </div>
  );
}

function RelevanceBadge({ score }: { score: number }) {
  const tone =
    score >= 85
      ? 'text-success-fg border-success/40 bg-success/10'
      : score >= 70
        ? 'text-accent border-accent/40 bg-accent/10'
        : 'text-muted border-border bg-surface';
  return (
    <div className={clsx('shrink-0 text-center rounded-md border px-3 py-1.5', tone)}>
      <div className="text-base font-semibold leading-none">{score}</div>
      <div className="text-xs uppercase tracking-wide opacity-70 mt-0.5">match</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function Notice({
  tone,
  children,
  onDismiss,
}: {
  tone: 'info' | 'error';
  children: React.ReactNode;
  onDismiss: () => void;
}) {
  return (
    <div
      className={clsx(
        'mb-4 rounded-lg border px-4 py-3 text-sm flex items-start gap-3',
        tone === 'error'
          ? 'bg-danger/10 border-danger/40 text-danger'
          : 'bg-surface/60 border-border text-muted',
      )}
    >
      <span className="flex-1">{children}</span>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100">
        <X size={14} />
      </button>
    </div>
  );
}

// EmptyState now lives in @/components/ui — shared across every screen
// that can be empty, not just this one.
