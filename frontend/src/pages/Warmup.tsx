// The warm-up screen.
//
// This is where someone ties in a fresh account and watches it become a real
// one. Two things have to be obvious at a glance: where the account is in the
// programme, and why it isn't allowed to do more yet — because the answer to
// "why hasn't it sent anything" is almost always "it hasn't earned it", and
// that needs to read as the system working rather than the system stuck.

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Heart,
  Lock,
  MessageSquare,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserPlus,
} from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, preflight, warmupApi } from '@/lib/api';
import type { Funnel, HealthVerdict, PreflightReport } from '@/types';

const STAGE_ICON: Record<string, typeof Heart> = {
  observe: Activity,
  react: Heart,
  converse: MessageSquare,
  publish: Sparkles,
  connect: UserPlus,
  full: ShieldCheck,
};

const VERDICT_TONE: Record<HealthVerdict, string> = {
  healthy: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200',
  caution: 'bg-amber-500/10 border-amber-500/40 text-amber-200',
  danger: 'bg-red-500/10 border-red-500/40 text-red-200',
  unknown: 'bg-slate-700/40 border-slate-600 text-slate-300',
};

export function Warmup() {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState('');
  const [report, setReport] = useState<PreflightReport | null>(null);

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });
  const { data: programme } = useQuery({
    queryKey: ['warmup-program'],
    queryFn: warmupApi.program,
  });

  useEffect(() => {
    if (!accountId && accounts.length) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  const { data: today, isLoading } = useQuery({
    queryKey: ['warmup-today', accountId],
    queryFn: () => warmupApi.today(accountId),
    enabled: !!accountId,
    refetchInterval: 60_000,
  });

  const runPreflight = useMutation({
    mutationFn: () => preflight(accountId),
    onSuccess: setReport,
  });

  const togglePause = useMutation({
    mutationFn: (paused: boolean) => warmupApi.pause(accountId, paused),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['warmup-today'] }),
  });

  if (!accounts.length) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20 text-center">
        <ShieldCheck className="mx-auto text-slate-600 mb-4" size={40} />
        <h2 className="text-xl font-semibold text-slate-200">No account connected</h2>
        <p className="text-slate-400 mt-2">
          Connect a LinkedIn account and it will start warming up automatically.
        </p>
        <a href="/accounts" className="btn-primary inline-flex mt-5">
          Connect an account
        </a>
      </div>
    );
  }

  const stages = programme?.stages ?? [];
  const currentIndex = stages.findIndex((s) => s.key === today?.stage);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Warm-up</h1>
          <p className="text-slate-400 mt-1">
            A new account earns its way to outreach over about{' '}
            {programme?.minimum_days_to_outreach ?? 21} days. Nothing is skipped.
          </p>
        </div>

        <div className="flex items-end gap-2 flex-wrap">
          <label className="flex flex-col gap-1 min-w-0">
            <span className="text-xs text-slate-400">Account</span>
            <select
              value={accountId}
              onChange={(e) => {
                setAccountId(e.target.value);
                setReport(null);
              }}
              className="select min-w-0"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name ?? 'Unnamed account'}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => runPreflight.mutate()}
            disabled={runPreflight.isPending}
            className="btn-ghost shrink-0 whitespace-nowrap"
            title="Read-only check — sends nothing"
          >
            <RefreshCw
              size={15}
              className={runPreflight.isPending ? 'animate-spin' : ''}
            />
            Test connection
          </button>
        </div>
      </header>

      {report && <PreflightPanel report={report} onDismiss={() => setReport(null)} />}

      {isLoading || !today ? (
        <div className="flex justify-center py-16 text-slate-400">
          <RefreshCw className="animate-spin" />
        </div>
      ) : (
        <>
          {/* Health */}
          <div
            className={clsx(
              'rounded-xl border p-4 mb-6 flex items-start gap-3',
              VERDICT_TONE[today.health.verdict],
            )}
          >
            {today.health.verdict === 'healthy' ? (
              <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium">{today.health.headline}</p>
              {today.health.advice.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm opacity-90">
                  {today.health.advice.map((a) => (
                    <li key={a}>· {a}</li>
                  ))}
                </ul>
              )}
            </div>
            <button
              onClick={() => togglePause.mutate(!today.paused)}
              className="btn-ghost shrink-0"
            >
              {today.paused ? <Play size={15} /> : <Pause size={15} />}
              {today.paused ? 'Resume' : 'Pause'}
            </button>
          </div>

          {/* Funnel */}
          <FunnelStrip funnel={today.health.funnel} />

          {/* Stage roadmap */}
          <section className="mb-8">
            <h2 className="text-sm font-medium text-slate-300 mb-3">Programme</h2>
            <div className="space-y-2">
              {stages.map((stage, index) => (
                <StageRow
                  key={stage.key}
                  stage={stage}
                  state={
                    index < currentIndex
                      ? 'done'
                      : index === currentIndex
                        ? 'current'
                        : 'locked'
                  }
                  status={index === currentIndex ? today : undefined}
                />
              ))}
            </div>
          </section>

          {/* Today */}
          <section>
            <h2 className="text-sm font-medium text-slate-300 mb-3">
              Today&rsquo;s activity
            </h2>
            <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-5">
              {today.plan.notes.length > 0 && (
                <ul className="mb-4 space-y-1">
                  {today.plan.notes.map((note) => (
                    <li key={note} className="text-xs text-slate-400">
                      · {note}
                    </li>
                  ))}
                </ul>
              )}

              {today.plan.actions.length === 0 ? (
                <p className="text-sm text-slate-500">
                  Nothing scheduled today.
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-3 mb-4">
                    {Object.entries(today.plan.counts).map(([action, count]) => (
                      <span
                        key={action}
                        className="px-3 py-1.5 rounded-lg bg-slate-900/70 text-sm"
                      >
                        <span className="text-slate-100 font-semibold">{count}</span>{' '}
                        <span className="text-slate-400">
                          {action}
                          {count === 1 ? '' : 's'}
                        </span>
                      </span>
                    ))}
                  </div>
                  <ol className="space-y-1.5 max-h-72 overflow-y-auto">
                    {today.plan.actions.map((item, i) => (
                      <li
                        key={`${item.action}-${i}`}
                        className="flex items-baseline gap-3 text-sm"
                      >
                        <time className="text-slate-500 tabular-nums shrink-0">
                          {new Date(item.at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </time>
                        <span className="text-slate-200 capitalize">{item.action}</span>
                        <span className="text-slate-500 text-xs truncate">
                          {item.reason}
                        </span>
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StageRow({
  stage,
  state,
  status,
}: {
  stage: { key: string; name: string; intent: string; min_days: number; allowed: string[] };
  state: 'done' | 'current' | 'locked';
  status?: { days_in_stage: number; progress: string[]; blockers: string[] };
}) {
  const Icon = STAGE_ICON[stage.key] ?? Activity;

  return (
    <motion.div
      layout
      className={clsx(
        'rounded-xl border p-4',
        state === 'current'
          ? 'bg-purple-500/10 border-purple-500/40'
          : state === 'done'
            ? 'bg-slate-800/40 border-slate-700'
            : 'bg-slate-800/20 border-slate-800',
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={clsx(
            'mt-0.5 shrink-0',
            state === 'done'
              ? 'text-emerald-400'
              : state === 'current'
                ? 'text-purple-300'
                : 'text-slate-600',
          )}
        >
          {state === 'done' ? (
            <CheckCircle2 size={18} />
          ) : state === 'locked' ? (
            <Lock size={18} />
          ) : (
            <Icon size={18} />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3
              className={clsx(
                'font-medium',
                state === 'locked' ? 'text-slate-500' : 'text-slate-100',
              )}
            >
              {stage.name}
            </h3>
            {state === 'current' && status && (
              <span className="text-xs text-purple-300">
                day {status.days_in_stage + 1}
                {stage.min_days ? ` of ${stage.min_days}+` : ''}
              </span>
            )}
          </div>
          <p
            className={clsx(
              'text-sm mt-0.5',
              state === 'locked' ? 'text-slate-600' : 'text-slate-400',
            )}
          >
            {stage.intent}
          </p>

          <div className="flex flex-wrap gap-1.5 mt-2">
            {stage.allowed.map((action) => (
              <span
                key={action}
                className={clsx(
                  'px-2 py-0.5 rounded text-xs',
                  state === 'locked'
                    ? 'bg-slate-800 text-slate-600'
                    : 'bg-slate-700/60 text-slate-300',
                )}
              >
                {action}
              </span>
            ))}
          </div>

          {state === 'current' && status && (
            <div className="mt-3 space-y-1">
              {status.progress.map((p) => (
                <div key={p} className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <Check size={12} />
                  {p}
                </div>
              ))}
              {status.blockers.map((b) => (
                <div key={b} className="flex items-center gap-1.5 text-xs text-slate-400">
                  <Clock size={12} />
                  {b}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export function FunnelStrip({ funnel }: { funnel: Partial<Funnel> }) {
  const steps = [
    { label: 'Invited', value: funnel.invites_sent ?? 0 },
    {
      label: 'Accepted',
      value: funnel.invites_accepted ?? 0,
      rate: funnel.acceptance_rate,
    },
    { label: 'Replied', value: funnel.replies ?? 0, rate: funnel.reply_rate },
    { label: 'Interested', value: funnel.interested ?? 0 },
    { label: 'Booked', value: funnel.booked ?? 0 },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-6">
      {steps.map((step) => (
        <div
          key={step.label}
          className="rounded-xl bg-slate-800/60 border border-slate-700 p-3"
        >
          <div className="text-xs text-slate-400">{step.label}</div>
          <div className="text-xl font-semibold text-slate-100 mt-0.5">{step.value}</div>
          {typeof step.rate === 'number' && (
            <div className="text-[11px] text-slate-500 mt-0.5">{step.rate}%</div>
          )}
        </div>
      ))}
    </div>
  );
}

function PreflightPanel({
  report,
  onDismiss,
}: {
  report: PreflightReport;
  onDismiss: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'rounded-xl border p-5 mb-6',
        report.ok
          ? 'bg-emerald-500/10 border-emerald-500/40'
          : 'bg-red-500/10 border-red-500/40',
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium text-slate-100">{report.summary}</h3>
          <p className="text-xs text-slate-400 mt-1">
            Read-only check — nothing was liked, connected, messaged or posted.
          </p>
        </div>
        <button onClick={onDismiss} className="btn-ghost shrink-0">
          Dismiss
        </button>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 mt-4">
        {report.checks.map((check) => (
          <div
            key={check.name}
            className="flex items-start gap-2 rounded-lg bg-slate-900/50 p-3"
          >
            {check.ok ? (
              <CheckCircle2 size={15} className="text-emerald-400 mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle size={15} className="text-amber-400 mt-0.5 shrink-0" />
            )}
            <div className="min-w-0">
              <div className="text-sm text-slate-200">{check.label}</div>
              {check.error && (
                <div className="text-xs text-slate-400 mt-0.5 break-words">
                  {check.error}
                </div>
              )}
              {!check.ok && check.impact && (
                <div className="text-xs text-slate-500 mt-1">{check.impact}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {report.next_steps.length > 0 && (
        <ul className="mt-4 space-y-1">
          {report.next_steps.map((s) => (
            <li key={s} className="text-sm text-slate-300">
              · {s}
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}
