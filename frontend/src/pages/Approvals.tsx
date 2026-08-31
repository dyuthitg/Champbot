// The approval queue.
//
// This is the screen the product is built around: the agent proposes who to
// contact and what to say, and a human decides. Every card has to answer three
// questions fast — who is this person, why them, and is this message something
// I'd be happy to have sent under my name.

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  Ban,
  Check,
  ExternalLink,
  Loader2,
  MessageSquare,
  Pencil,
  Send,
  Sparkles,
  UserPlus,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, outreachApi, targetingApi } from '@/lib/api';
import type { Suggestion, SuggestionAction } from '@/types';
import { Card, Chip, Button, EmptyState } from '@/components/ui';

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

export function Approvals() {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState<string>('');
  const [icpId, setIcpId] = useState<string>('');
  const [banner, setBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ['suggestions', accountId],
    queryFn: () => outreachApi.list(accountId || undefined, 'pending'),
    enabled: !!accountId,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['suggestions'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

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
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 className="animate-spin" />
        </div>
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<Send size={40} />}
          title="Nothing waiting for review"
          body="Import some people on the Targeting page, then use “Suggest who to contact”. Only strong matches make it this far."
        />
      ) : (
        <div className="space-y-4">
          <AnimatePresence mode="popLayout">
            {suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onResolved={invalidate}
                onError={setError}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function SuggestionCard({
  suggestion,
  onResolved,
  onError,
}: {
  suggestion: Suggestion;
  onResolved: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(suggestion.final_text ?? suggestion.draft_text ?? '');
  const meta = ACTION_META[suggestion.action] ?? ACTION_META.connect;
  const Icon = meta.icon;
  const target = suggestion.target;

  const fail = (err: any, fallback: string) =>
    onError(err?.response?.data?.detail ?? fallback);

  const approve = useMutation({
    mutationFn: () =>
      outreachApi.approve(suggestion.id, editing ? text : undefined),
    onSuccess: onResolved,
    onError: (err) => fail(err, 'Could not approve this suggestion'),
  });

  const reject = useMutation({
    mutationFn: (suppress: boolean) => outreachApi.reject(suggestion.id, suppress),
    onSuccess: onResolved,
    onError: (err) => fail(err, 'Could not reject this suggestion'),
  });

  const busy = approve.isPending || reject.isPending;
  const overLimit = suggestion.action === 'connect' && text.length > 300;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <Card padded={false} className="overflow-hidden">
      {/* Who */}
      <div className="p-5 pb-3 flex items-start gap-4">
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
            <div
              className={clsx(
                'text-xs mt-1',
                overLimit ? 'text-danger' : 'text-muted',
              )}
            >
              {text.length}
              {suggestion.action === 'connect' ? ' / 300 characters' : ' characters'}
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

        {suggestion.quality_warnings.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5">
            {suggestion.quality_warnings.map((warning) => (
              <Chip key={warning} tone="accent" icon={<AlertTriangle size={11} />} className="justify-start w-fit">
                {warning}
              </Chip>
            ))}
          </div>
        )}
      </div>

      {/* Decide */}
      <div className="px-5 py-3 bg-slate-900/40 border-t border-border flex flex-wrap items-center gap-2">
        <Button
          variant="success"
          onClick={() => approve.mutate()}
          disabled={busy || overLimit || !text.trim()}
          icon={approve.isPending ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
        >
          Approve{editing ? ' edit' : ''} &amp; schedule
        </Button>

        <Button variant="ghost" onClick={() => setEditing((v) => !v)} disabled={busy} icon={<Pencil size={15} />}>
          {editing ? 'Cancel edit' : 'Edit'}
        </Button>

        <Button variant="ghost" onClick={() => reject.mutate(false)} disabled={busy} icon={<X size={15} />}>
          Skip
        </Button>

        {/* Still fires on one click — the confirm step is scoped for the
            Week 2 review-queue rebuild, not this token/component pass. */}
        <Button
          variant="danger"
          onClick={() => reject.mutate(true)}
          disabled={busy}
          icon={<Ban size={15} />}
          className="ml-auto"
          title="Never contact this person again"
        >
          Never contact
        </Button>
      </div>
      </Card>
    </motion.div>
  );
}

function RelevanceBadge({ score }: { score: number }) {
  const tone =
    score >= 85
      ? 'text-success border-success/40 bg-success/10'
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
