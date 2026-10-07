// Multi-account overview: every connected account in the org at a glance.
//
// This is the admin view — one row per account showing what's waiting for
// review, what's queued, what went out today, and how much headroom is left
// under each account's caps.

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  History,
  Inbox,
  Loader2,
  Moon,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Users,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { formatDistanceToNow, isToday, isYesterday } from 'date-fns';
import { outreachApi } from '@/lib/api';
import { useGeneralWebSocket } from '@/hooks/useWebSocket';
import { Chip } from '@/components/ui/Chip';
import { Button } from '@/components/ui/Button';
import type { AccountStats, ApprovalLevel } from '@/types';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// A small personal touch instead of the same static subtitle at 9am and
// 9pm -- costs nothing, and it's the first line anyone reads all day.
function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

// A deterministic colour per account name so the same account always gets
// the same avatar colour, and five accounts in a list don't all look the
// same grey. Nothing clever -- just a stable hash into a small fixed palette.
const AVATAR_PALETTE = [
  'bg-blue-500/20 text-blue-300',
  'bg-purple-500/20 text-purple-300',
  'bg-emerald-500/20 text-emerald-300',
  'bg-amber-500/20 text-amber-300',
  'bg-pink-500/20 text-pink-300',
  'bg-cyan-500/20 text-cyan-300',
] as const;

function avatarTone(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
}

// "Today" / "Yesterday" reads in an instant; a repeated full date for every
// row this week doesn't.
function dayLabel(date: Date) {
  if (isToday(date)) return 'Today';
  if (isYesterday(date)) return 'Yesterday';
  return date.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

interface SessionProblem {
  text: string;
  cta?: { label: string; href: string };
}

// Words a non-technical person reads at 9am and knows exactly what to do —
// not a status enum. `since` is already "2 hours ago"-shaped.
//
// Only `auth_required` gets a "Reconnect" button: that's the one case a new
// cookie actually fixes. A challenged account (rate_limited/suspended) needs
// the opposite of a retry — src/outreach/health.py's own advice for these is
// "clear the checkpoint in a browser, then leave it 48 hours" — so pointing
// someone at Reconnect there would invite exactly the retry behaviour that
// gets an account further restricted.
function sessionProblem(account: AccountStats, since: string): SessionProblem | null {
  const name = account.display_name ?? 'This account';
  switch (account.status) {
    case 'auth_required':
      return {
        text: `LinkedIn session expired for ${name}, ${since}.`,
        cta: { label: 'Reconnect', href: '/accounts' },
      };
    case 'suspended':
      return {
        text: `${name} was suspended by LinkedIn, ${since}. Clear the checkpoint by signing in through a normal browser, then wait 48 hours before re-verifying here.`,
      };
    case 'rate_limited':
      return {
        text: `LinkedIn pushed back on ${name} ${since} — invitations paused to protect the account. Clear the checkpoint in a browser and leave it for 48 hours before re-verifying.`,
      };
    case 'error':
      return {
        text: `${name} hit an error and stopped, ${since}.`,
      };
    default:
      return null;
  }
}

export function Dashboard() {
  const reduced = prefersReducedMotion();
  const { isConnected } = useGeneralWebSocket();

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: outreachApi.dashboard,
    refetchInterval: 15_000,
  });

  const { data: activity = [] } = useQuery({
    queryKey: ['activity'],
    queryFn: () => outreachApi.activity(),
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-24 text-slate-400">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  const totals = data?.totals ?? {};
  const accounts = data?.accounts ?? [];

  // What someone checks at 9am to know the bot is alive: every account with a
  // specific, dated problem, gathered into one list at the top of the screen
  // instead of a status dot someone has to go read logs to explain.
  const problems = accounts.flatMap((account) => {
    const rows: { key: string; text: string; cta?: { label: string; href: string } }[] = [];
    const problem = sessionProblem(
      account,
      account.status_since
        ? formatDistanceToNow(new Date(account.status_since), { addSuffix: true })
        : 'recently',
    );
    if (problem) {
      rows.push({
        key: `${account.account_id}-session`,
        text: problem.text,
        cta: problem.cta,
      });
    }
    if (account.last_run_ok === false && account.last_error) {
      const since = account.last_error_at
        ? formatDistanceToNow(new Date(account.last_error_at), { addSuffix: true })
        : 'on the last run';
      rows.push({
        key: `${account.account_id}-run`,
        text: `${account.display_name ?? 'This account'}'s last run failed ${since}: ${account.last_error}`,
      });
    }
    return rows;
  });

  return (
    <div className="max-w-7xl mx-auto px-5 sm:px-8 py-10">
      {/* Hero: one clearly different, colourful panel up top that the rest of
          the page (plain slate cards) doesn't try to compete with -- a
          single strong flourish reads better than the same soft touch
          repeated everywhere. */}
      <header className="relative mb-9 rounded-3xl border border-slate-700/60 overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-br from-purple-600/25 via-slate-900/40 to-blue-600/10"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -top-20 -right-14 w-96 h-96 rounded-full bg-purple-500/20 blur-3xl"
        />
        <div className="relative p-6 sm:p-10">
          <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
            <div>
              <span className="text-sm font-semibold uppercase tracking-wider text-purple-300/70">
                Overview
              </span>
              <h1 className="font-display text-4xl sm:text-5xl font-bold bg-gradient-to-r from-purple-300 via-purple-200 to-amber-200 bg-clip-text text-transparent mt-1">
                {greeting()}
              </h1>
              <p className="text-slate-300/90 mt-2 text-base flex items-center gap-2 flex-wrap">
                Every connected account, and what each of them is doing.
                {problems.length === 0 && accounts.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-sm font-medium text-success-fg bg-success/10 px-2.5 py-1 rounded-full">
                    <Sparkles size={13} />
                    All running smoothly
                  </span>
                )}
              </p>
            </div>
            {isConnected && (
              <span className="inline-flex items-center gap-1.5 text-sm text-success-fg mt-1 bg-success/10 px-3 py-1.5 rounded-full">
                <motion.span
                  className="w-2 h-2 rounded-full bg-success-fg"
                  animate={
                    reduced
                      ? undefined
                      : { opacity: [1, 0.3, 1], transition: { duration: 2, repeat: Infinity } }
                  }
                />
                Live
              </span>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={Users} label="Accounts" value={totals.accounts ?? 0} tone="blue" />
            <Stat
              icon={Inbox}
              label="Waiting for review"
              value={totals.pending_review ?? 0}
              tone="purple"
              href="/approvals"
            />
            <Stat icon={Clock} label="Queued to send" value={totals.scheduled ?? 0} tone="amber" />
            <Stat icon={Send} label="Sent today" value={totals.sent_today ?? 0} tone="emerald" />
          </div>

          {/* Quick actions: the three things someone opens this page to
              actually go do, one click away instead of a trip through the
              nav for each. */}
          <div className="flex flex-wrap gap-2.5 mt-6">
            <Link
              to="/approvals"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-100 bg-white/10 hover:bg-white/15 px-4 py-2 rounded-full transition-colors"
            >
              <Inbox size={14} />
              Review queue
              <ArrowRight size={13} className="opacity-60" />
            </Link>
            <Link
              to="/accounts"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-100 bg-white/10 hover:bg-white/15 px-4 py-2 rounded-full transition-colors"
            >
              <UserPlus size={14} />
              Connect account
            </Link>
            <Link
              to="/campaigns/new"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-100 bg-white/10 hover:bg-white/15 px-4 py-2 rounded-full transition-colors"
            >
              <Plus size={14} />
              New campaign
            </Link>
          </div>
        </div>
      </header>

      {problems.length > 0 && (
        <motion.div
          initial={reduced ? undefined : { opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 rounded-xl bg-danger/10 border border-danger/40 overflow-hidden"
        >
          <div className="px-5 py-2.5 flex items-center gap-2 text-danger-fg text-sm font-semibold uppercase tracking-wide bg-danger/10 border-b border-danger/30">
            <AlertTriangle size={15} />
            Needs attention
          </div>
          <ul className="divide-y divide-danger/20">
            {problems.map((p) => (
              <li key={p.key} className="px-5 py-3.5 flex items-center justify-between gap-4 flex-wrap">
                <span className="text-base text-slate-100">{p.text}</span>
                {p.cta && (
                  <Link to={p.cta.href} className="btn-ghost shrink-0 text-danger-fg">
                    {p.cta.label}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {accounts.length === 0 ? (
        <div className="text-center py-20 rounded-2xl border border-dashed border-slate-700">
          <div className="mx-auto mb-5 w-20 h-20 rounded-full bg-purple-500/10 flex items-center justify-center">
            <Users className="text-purple-300" size={34} />
          </div>
          <h2 className="text-xl font-semibold text-slate-200">No accounts yet</h2>
          <p className="text-slate-400 mt-2 mb-5 text-base">
            Connect a LinkedIn account to start suggesting outreach.
          </p>
          <Link to="/accounts" className="btn-primary inline-flex">
            Connect a LinkedIn account
          </Link>
        </div>
      ) : (
        <section className="mb-10">
          <SectionHeading icon={Users} label="Accounts" />
          <div className="space-y-3">
            {accounts.map((account, i) => (
              <AccountCard key={account.account_id} account={account} index={i} />
            ))}
          </div>
        </section>
      )}

      <section>
        <SectionHeading icon={History} label="Recent activity" />
        {activity.length === 0 ? (
          <p className="text-base text-slate-500">
            Nothing sent yet. Approved outreach appears here as it goes out.
          </p>
        ) : (
          <div className="rounded-xl bg-slate-800/60 border border-slate-700 overflow-hidden">
            {(() => {
              let lastDay: string | null = null;
              return activity.slice(0, 15).map((item, i) => {
                const occurred = item.occurred_at ? new Date(item.occurred_at) : null;
                const label = occurred ? dayLabel(occurred) : null;
                const showDivider = label !== null && label !== lastDay;
                lastDay = label ?? lastDay;

                return (
                  <div key={item.id}>
                    {showDivider && (
                      <div
                        className={clsx(
                          'px-5 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 bg-slate-900/40',
                          i > 0 && 'border-t border-slate-700',
                        )}
                      >
                        {label}
                      </div>
                    )}
                    <motion.div
                      initial={reduced ? undefined : { opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: Math.min(i, 10) * 0.02, duration: 0.25 }}
                      className={clsx(
                        'p-5 flex items-start gap-3.5 hover:bg-slate-800 transition-colors',
                        !showDivider && i > 0 && 'border-t border-slate-700',
                      )}
                    >
                      <ActivityIcon status={item.status} />
                      <div className="min-w-0 flex-1">
                        <div className="text-base text-slate-200">
                          <span className="capitalize font-medium">{item.action}</span>
                          {item.target_name ? (
                            <span className="text-slate-400"> → {item.target_name}</span>
                          ) : (
                            ''
                          )}
                        </div>
                        {item.text && (
                          <p className="text-sm text-slate-500 mt-0.5 truncate">{item.text}</p>
                        )}
                        {item.error && <p className="text-sm text-red-400 mt-0.5">{item.error}</p>}
                      </div>
                      {occurred && (
                        <time
                          title={occurred.toLocaleString()}
                          className="text-sm text-slate-500 shrink-0 tabular-nums"
                        >
                          {formatDistanceToNow(occurred, { addSuffix: true })}
                        </time>
                      )}
                    </motion.div>
                  </div>
                );
              });
            })()}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeading({ icon: Icon, label }: { icon: typeof Users; label: string }) {
  return (
    <h2 className="flex items-center gap-2.5 text-base font-semibold text-slate-200 mb-4">
      <span className="w-8 h-8 rounded-lg bg-slate-700/60 text-slate-300 flex items-center justify-center">
        <Icon size={16} />
      </span>
      {label}
    </h2>
  );
}

function ActivityIcon({ status }: { status: string }) {
  if (status === 'sent') {
    return (
      <span className="mt-0.5 w-6 h-6 rounded-full bg-success/15 text-success-fg flex items-center justify-center shrink-0">
        <CheckCircle2 size={14} />
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="mt-0.5 w-6 h-6 rounded-full bg-danger/15 text-danger-fg flex items-center justify-center shrink-0">
        <XCircle size={14} />
      </span>
    );
  }
  return (
    <span className="mt-0.5 w-6 h-6 rounded-full bg-warn/15 text-warn flex items-center justify-center shrink-0">
      <Clock size={14} />
    </span>
  );
}

const STAT_TONE = {
  blue: { icon: 'bg-blue-500/20 text-blue-300', card: 'bg-blue-500/10 border-blue-500/30' },
  purple: { icon: 'bg-purple-500/20 text-purple-300', card: 'bg-purple-500/10 border-purple-500/30' },
  amber: { icon: 'bg-amber-500/20 text-amber-300', card: 'bg-amber-500/10 border-amber-500/30' },
  emerald: { icon: 'bg-emerald-500/20 text-emerald-300', card: 'bg-emerald-500/10 border-emerald-500/30' },
} as const;

function Stat({
  icon: Icon,
  label,
  value,
  tone,
  href,
}: {
  icon: typeof Users;
  label: string;
  value: number;
  tone: keyof typeof STAT_TONE;
  href?: string;
}) {
  const reduced = prefersReducedMotion();
  const { icon, card } = STAT_TONE[tone];

  const body = (
    <motion.div
      whileHover={reduced ? undefined : { y: -3, scale: 1.02 }}
      transition={{ type: 'spring', stiffness: 300 }}
      className={clsx('rounded-xl border p-5 flex items-center gap-4 backdrop-blur-sm', card)}
    >
      <div className={clsx('w-14 h-14 rounded-xl flex items-center justify-center shrink-0', icon)}>
        <Icon size={26} />
      </div>
      <div className="min-w-0">
        <div className="font-display text-4xl font-bold text-slate-50 leading-none">{value}</div>
        <div className="text-sm text-slate-300/80 mt-2">{label}</div>
      </div>
    </motion.div>
  );
  return href ? <Link to={href}>{body}</Link> : body;
}

const CAP_ACTIONS = ['connect', 'message', 'comment', 'like'] as const;

function AccountCard({ account, index }: { account: AccountStats; index: number }) {
  const reduced = prefersReducedMotion();
  const runOk = account.last_run_ok;
  const name = account.display_name ?? 'Unnamed account';

  return (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.05, duration: 0.3 }}
      whileHover={reduced ? undefined : { y: -2 }}
      className={clsx(
        'rounded-xl bg-slate-800/60 border-y border-r border-slate-700 hover:border-slate-600 border-l-4 p-5 flex flex-wrap items-center gap-4 transition-colors',
        account.status === 'active' ? 'border-l-emerald-400' : 'border-l-amber-400',
      )}
    >
      <div className="min-w-0 flex-1 basis-full sm:basis-auto flex items-center gap-3.5">
        <div
          className={clsx(
            'w-11 h-11 rounded-full flex items-center justify-center text-sm font-semibold shrink-0',
            avatarTone(name),
          )}
        >
          {initials(name)}
        </div>
        <div className="min-w-0">
          {/* flex-wrap here, not truncate-under-pressure: when the row runs
              out of room, "outreach" drops to its own line rather than
              squeezing the account name down to nothing while the mode
              label survives (Week 1 audit — the name used to lose that
              fight every time). */}
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base sm:text-lg text-slate-100 font-semibold truncate max-w-full">
              {name}
            </h3>
            <span className="text-xs text-slate-500 shrink-0">
              {account.mode === 'account_based_engagement' ? 'engagement' : 'outreach'}
            </span>
          </div>
          <div className="text-sm text-slate-500 mt-1">
            {account.connects_sent} invitations · {account.messages_sent} messages sent
            all-time
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-5 sm:gap-6 text-center divide-x divide-slate-700/60">
        <Metric label="to review" value={account.pending_review} accent />
        <Metric label="queued" value={account.scheduled} />
        <Metric label="today" value={account.sent_today} />
        <Metric
          label="invites left"
          value={account.remaining_today?.connect ?? 0}
        />
        {account.failed > 0 && <Metric label="failed" value={account.failed} danger />}
      </div>

      <Link to="/approvals" className="btn-ghost shrink-0">
        <Activity size={15} />
        Review
      </Link>

      {/* Run status: what someone checks at 9am to know the bot is alive. */}
      <div className="w-full flex flex-wrap items-center gap-x-4 gap-y-2 pt-4 mt-1 border-t border-slate-700 text-sm">
        <span className="text-slate-500">
          Last run{' '}
          <span className="text-slate-300">
            {account.last_run_at
              ? formatDistanceToNow(new Date(account.last_run_at), { addSuffix: true })
              : 'never — not scheduled yet'}
          </span>
        </span>

        {runOk === false && (
          <Chip tone="danger" icon={<AlertTriangle size={11} />}>
            last run failed
          </Chip>
        )}

        {account.quiet_hours_now && (
          <Chip tone="neutral" icon={<Moon size={11} />}>
            Quiet hours — this is expected, not a bug
          </Chip>
        )}
        {account.weekend_now && <Chip tone="neutral">Weekend — reduced pace</Chip>}
      </div>

      {account.approval && (
        <ApprovalRow accountId={account.account_id} approval={account.approval} />
      )}

      {/* Daily headroom, as a bar instead of a fraction -- "3/50" takes a
          beat to parse as "barely used"; a mostly-empty bar reads instantly. */}
      <div className="w-full grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 mt-1 border-t border-slate-700">
        {CAP_ACTIONS.map((action) => {
          const cap = account.caps_today?.[action];
          if (!cap) return null;
          return <CapBar key={action} label={action} used={cap.used} cap={cap.cap} tracked={cap.tracked} />;
        })}
      </div>
    </motion.div>
  );
}

// Step-down rule (agreed with Champ, 7 Oct): how many comments a person
// checks right now, how close the account is to checking fewer, and the
// "a bad comment got out" button that sends it straight back to 100%.
function ApprovalRow({ accountId, approval }: { accountId: string; approval: ApprovalLevel }) {
  const queryClient = useQueryClient();
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState('');
  const report = useMutation({
    mutationFn: () => outreachApi.resetApproval(accountId, reason.trim()),
    onSuccess: () => {
      setReporting(false);
      setReason('');
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const progress =
    approval.next_check_percent === null
      ? 'lowest level — stays here'
      : `${approval.clean_streak} of ${approval.clean_needed} clean days toward ${approval.next_check_percent}%`;

  return (
    <div className="w-full pt-4 mt-1 border-t border-slate-700 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex items-center gap-1.5 text-slate-500">
          <ShieldCheck size={14} />
          Comments checked
          <span className="text-slate-100 font-semibold">{approval.check_percent}%</span>
        </span>
        <span className="text-slate-400">{progress}</span>
        {approval.last_reset_reason && approval.stage === 1 && approval.clean_streak === 0 && (
          // Not a Chip: chips never wrap, and a reset reason is a sentence
          // that got clipped mid-word at phone width.
          <span className="rounded-lg bg-warn/15 text-warn px-2 py-0.5 text-xs font-medium max-w-full break-words">
            Back to 100%: {approval.last_reset_reason}
          </span>
        )}
        {approval.check_percent < 100 && !reporting && (
          <button
            onClick={() => setReporting(true)}
            className="ml-auto text-xs text-danger-fg hover:underline min-h-[44px] sm:min-h-0"
          >
            Report a bad comment
          </button>
        )}
      </div>
      {reporting && (
        <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2">
          <input
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && reason.trim()) report.mutate();
              if (e.key === 'Escape') setReporting(false);
            }}
            placeholder="What was wrong with it?"
            className="flex-1 min-w-0 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <Button
            variant="danger"
            disabled={!reason.trim() || report.isPending}
            onClick={() => report.mutate()}
            className="px-2.5 py-1 text-xs shrink-0"
          >
            Back to checking 100%
          </Button>
          <Button onClick={() => setReporting(false)} className="px-2.5 py-1 text-xs shrink-0">
            Cancel
          </Button>
        </div>
      )}
      {report.isError && (
        <p className="mt-2 text-xs text-danger-fg">Could not reset — try again.</p>
      )}
    </div>
  );
}

function CapBar({
  label,
  used,
  cap,
  tracked,
}: {
  label: string;
  used: number;
  cap: number;
  tracked: boolean;
}) {
  const pct = cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  const fill = pct >= 100 ? 'bg-danger' : pct >= 75 ? 'bg-warn' : 'bg-emerald-400';

  return (
    <div>
      <div className="flex items-baseline justify-between text-xs mb-1.5">
        <span className="capitalize text-slate-400">{label}</span>
        <span className="text-slate-300 tabular-nums">
          {tracked ? `${used}/${cap}` : 'uncapped'}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-700/70 overflow-hidden">
        {tracked && (
          <div
            className={clsx('h-full rounded-full transition-all', fill)}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
  danger,
}: {
  label: string;
  value: number;
  accent?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="pl-5 first:pl-0">
      <div
        className={clsx(
          'text-xl font-semibold leading-none',
          danger ? 'text-red-400' : accent && value > 0 ? 'text-purple-300' : 'text-slate-200',
        )}
      >
        {value}
      </div>
      <div className="text-xs uppercase tracking-wide text-slate-500 mt-1.5">
        {label}
      </div>
    </div>
  );
}
