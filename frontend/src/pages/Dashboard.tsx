// Multi-account overview: every connected account in the org at a glance.
//
// This is the admin view — one row per account showing what's waiting for
// review, what's queued, what went out today, and how much headroom is left
// under each account's caps.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  Clock,
  Inbox,
  Loader2,
  Moon,
  Send,
  Users,
} from 'lucide-react';
import { clsx } from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { outreachApi } from '@/lib/api';
import { Chip } from '@/components/ui/Chip';
import type { AccountStats } from '@/types';

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
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Overview</h1>
        <p className="text-slate-400 mt-1">
          Every connected account, and what each of them is doing.
        </p>
      </header>

      {problems.length > 0 && (
        <div className="mb-6 rounded-xl bg-danger/10 border border-danger/40 overflow-hidden">
          <div className="px-4 py-2 flex items-center gap-2 text-danger-fg text-xs font-semibold uppercase tracking-wide bg-danger/10 border-b border-danger/30">
            <AlertTriangle size={14} />
            Needs attention
          </div>
          <ul className="divide-y divide-danger/20">
            {problems.map((p) => (
              <li key={p.key} className="px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
                <span className="text-sm text-slate-100">{p.text}</span>
                {p.cta && (
                  <Link to={p.cta.href} className="btn-ghost shrink-0 text-danger-fg">
                    {p.cta.label}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <Stat icon={Users} label="Accounts" value={totals.accounts ?? 0} />
        <Stat
          icon={Inbox}
          label="Waiting for review"
          value={totals.pending_review ?? 0}
          highlight={(totals.pending_review ?? 0) > 0}
          href="/approvals"
        />
        <Stat icon={Clock} label="Queued to send" value={totals.scheduled ?? 0} />
        <Stat icon={Send} label="Sent today" value={totals.sent_today ?? 0} />
      </div>

      {accounts.length === 0 ? (
        <div className="text-center py-16">
          <Users className="mx-auto text-slate-600 mb-4" size={40} />
          <h2 className="text-lg font-semibold text-slate-200">No accounts yet</h2>
          <p className="text-slate-400 mt-2">
            <Link to="/accounts" className="text-purple-400 hover:underline">
              Connect a LinkedIn account
            </Link>{' '}
            to get started.
          </p>
        </div>
      ) : (
        <section className="mb-8">
          <h2 className="text-sm font-medium text-slate-300 mb-3">Accounts</h2>
          <div className="space-y-2">
            {accounts.map((account) => (
              <AccountCard key={account.account_id} account={account} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-medium text-slate-300 mb-3">Recent activity</h2>
        {activity.length === 0 ? (
          <p className="text-sm text-slate-500">
            Nothing sent yet. Approved outreach appears here as it goes out.
          </p>
        ) : (
          <div className="rounded-xl bg-slate-800/60 border border-slate-700 divide-y divide-slate-700">
            {activity.slice(0, 15).map((item) => (
              <div key={item.id} className="p-4 flex items-start gap-3">
                <span
                  className={clsx(
                    'mt-1 w-2 h-2 rounded-full shrink-0',
                    item.status === 'sent'
                      ? 'bg-emerald-400'
                      : item.status === 'failed'
                        ? 'bg-red-400'
                        : 'bg-amber-400',
                  )}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-200">
                    <span className="capitalize">{item.action}</span>
                    {item.target_name ? ` → ${item.target_name}` : ''}
                    <span className="text-slate-500 ml-2 text-xs">{item.status}</span>
                  </div>
                  {item.text && (
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{item.text}</p>
                  )}
                  {item.error && (
                    <p className="text-xs text-red-400 mt-0.5">{item.error}</p>
                  )}
                </div>
                {item.occurred_at && (
                  <time className="text-xs text-slate-500 shrink-0">
                    {new Date(item.occurred_at).toLocaleString()}
                  </time>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  highlight,
  href,
}: {
  icon: typeof Users;
  label: string;
  value: number;
  highlight?: boolean;
  href?: string;
}) {
  const body = (
    <motion.div
      whileHover={href ? { scale: 1.02 } : undefined}
      className={clsx(
        'rounded-xl border p-4',
        highlight
          ? 'bg-purple-500/10 border-purple-500/40'
          : 'bg-slate-800/60 border-slate-700',
      )}
    >
      <div className="flex items-center gap-2 text-slate-400 text-xs">
        <Icon size={14} />
        {label}
      </div>
      <div className="text-2xl font-semibold text-slate-100 mt-1">{value}</div>
    </motion.div>
  );
  return href ? <Link to={href}>{body}</Link> : body;
}

const CAP_ACTIONS = ['connect', 'message', 'comment', 'like'] as const;

function AccountCard({ account }: { account: AccountStats }) {
  const runOk = account.last_run_ok;
  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-4 flex flex-wrap items-center gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={clsx(
              'w-2 h-2 rounded-full',
              account.status === 'active' ? 'bg-emerald-400' : 'bg-amber-400',
            )}
          />
          <h3 className="text-slate-100 font-medium truncate">
            {account.display_name ?? 'Unnamed account'}
          </h3>
          <span className="text-xs text-slate-500">
            {account.mode === 'account_based_engagement' ? 'engagement' : 'outreach'}
          </span>
        </div>
        <div className="text-xs text-slate-500 mt-1">
          {account.connects_sent} invitations · {account.messages_sent} messages sent
          all-time
        </div>
      </div>

      <div className="flex gap-5 text-center">
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
      <div className="w-full flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-3 mt-1 border-t border-slate-700 text-xs">
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

        {CAP_ACTIONS.map((action) => {
          const cap = account.caps_today?.[action];
          if (!cap) return null;
          const atCap = cap.tracked && cap.used >= cap.cap;
          return (
            <Chip key={action} tone={atCap ? 'warn' : 'neutral'}>
              {action} {cap.used}/{cap.cap}
              {cap.week_cap ? ` (${cap.week_used}/${cap.week_cap} this week)` : ''}
              {!cap.tracked && ' — uncapped, no Redis'}
            </Chip>
          );
        })}

        {account.quiet_hours_now && (
          <Chip tone="neutral" icon={<Moon size={11} />}>
            Quiet hours — this is expected, not a bug
          </Chip>
        )}
        {account.weekend_now && <Chip tone="neutral">Weekend — reduced pace</Chip>}
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
    <div>
      <div
        className={clsx(
          'text-lg font-semibold leading-none',
          danger ? 'text-red-400' : accent && value > 0 ? 'text-purple-300' : 'text-slate-200',
        )}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500 mt-1">
        {label}
      </div>
    </div>
  );
}
