// How the review step is going: items reviewed, approval rate, edits per
// item and time to approve. Read-only -- the queue itself is the Approvals
// tab next door. Definitions live in backend/src/outreach/review_metrics.py.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import { AlertTriangle, BarChart3, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, outreachApi } from '@/lib/api';
import type { ReviewMetrics as Metrics, ReviewMetricsBucket } from '@/types';
import { Button, Card, EmptyState } from '@/components/ui';

const RANGES = [7, 30, 90] as const;

const ACTION_LABEL: Record<string, string> = {
  connect: 'Invitations',
  message: 'Messages',
  comment: 'Comments',
  like: 'Likes',
  follow: 'Follows',
};

/** 90 s -> "2m", 5400 s -> "1h 30m", 200000 s -> "2d 7h". Null is "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours}h ${minutes % 60}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days}d ${hours % 24}h` : `${days}d`;
}

const pct = (v: number | null) => (v == null ? '—' : `${v}%`);
const ratio = (v: number | null) => (v == null ? '—' : v.toFixed(2));

export function ReviewMetrics() {
  const [days, setDays] = useState<number>(7);
  const [accountId, setAccountId] = useState('');

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['review-metrics', days, accountId],
    queryFn: () => outreachApi.reviewMetrics(days, accountId),
    refetchInterval: 60_000,
  });

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-100">Review metrics</h1>
        <p className="text-slate-400 mt-1">
          How the approval queue is going: what got reviewed, how much was approved, how much
          needed fixing, and how long it waited.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3 mb-6 p-4 rounded-xl bg-slate-800/60 border border-slate-700">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Account</span>
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)} className="select">
            <option value="">All accounts</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name ?? 'Unnamed account'}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Period</span>
          <div role="radiogroup" aria-label="Period" className="flex rounded-lg border border-slate-600 overflow-hidden">
            {RANGES.map((r) => (
              <button
                key={r}
                role="radio"
                aria-checked={days === r}
                onClick={() => setDays(r)}
                className={clsx(
                  'px-3 py-2 min-h-[44px] sm:min-h-0 text-sm font-medium transition-colors',
                  days === r ? 'bg-accent text-white' : 'bg-slate-900 text-slate-300 hover:bg-slate-800',
                )}
              >
                {r} days
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted">
          <Loader2 className="animate-spin" size={22} />
          <span className="text-sm">Loading metrics…</span>
        </div>
      ) : isError || !data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <AlertTriangle className="text-danger" size={32} />
          <div>
            <p className="text-foreground font-medium">Couldn't load the metrics</p>
            <p className="text-muted text-sm mt-1">Your connection, or the server, might be down.</p>
          </div>
          <Button variant="ghost" onClick={() => refetch()}>Try again</Button>
        </div>
      ) : data.totals.reviewed === 0 ? (
        <>
          <QueueNow data={data} />
          <EmptyState
            icon={<BarChart3 size={40} />}
            title={`Nothing reviewed in the last ${data.days} days`}
            body={
              data.auto_approved
                ? `${data.auto_approved} comments were approved automatically by the step-down rule; those aren't counted here because nobody reviewed them.`
                : 'Approve or reject suggestions in the queue and the numbers show up here.'
            }
            cta={{ label: 'Open the queue', href: '/approvals' }}
          />
        </>
      ) : (
        <Loaded data={data} />
      )}
    </div>
  );
}

function Loaded({ data }: { data: Metrics }) {
  const t = data.totals;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat
          label="Items reviewed"
          value={String(t.reviewed)}
          sub={`${t.approved} approved · ${t.rejected} rejected`}
        />
        <Stat
          label="Approval rate"
          value={pct(t.approval_rate)}
          sub={`of ${t.reviewed} reviewed`}
        />
        <Stat
          label="Edits per item"
          value={ratio(t.edits_per_item)}
          sub={`${t.edited} of ${t.approved} approvals edited`}
        />
        <Stat
          label="Time to approve"
          value={formatDuration(t.median_seconds_to_approve)}
          sub={`median · 90% within ${formatDuration(t.p90_seconds_to_approve)}`}
        />
      </div>

      <QueueNow data={data} />

      <Card>
        <h2 className="text-sm font-semibold text-slate-200">Decisions per day</h2>
        <DailyChart daily={data.daily} />
      </Card>

      <Card padded={false}>
        <h2 className="text-sm font-semibold text-slate-200 px-5 pt-5 pb-3">By action</h2>
        <BucketTable
          rows={data.by_action.map((b) => ({ key: b.action, label: ACTION_LABEL[b.action] ?? b.action, bucket: b }))}
        />
      </Card>

      <details className="group">
        <summary className="cursor-pointer text-sm text-slate-400 hover:text-slate-200">
          Show the daily numbers as a table
        </summary>
        <Card padded={false} className="mt-3">
          <BucketTable
            rows={[...data.daily].reverse().map((d) => ({
              key: d.date,
              label: format(parseISO(d.date), 'EEE d MMM'),
              bucket: d,
            }))}
          />
        </Card>
      </details>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card className="!p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="font-display text-3xl font-semibold text-slate-100 mt-1 tabular-nums">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{sub}</div>
    </Card>
  );
}

function QueueNow({ data }: { data: Metrics }) {
  return (
    <p className="text-sm text-slate-400">
      <span className="text-slate-200 font-medium">{data.pending_now}</span> waiting for review now
      {data.oldest_pending_seconds != null && (
        <>
          {' '}· oldest has waited{' '}
          <span className="text-slate-200 font-medium">{formatDuration(data.oldest_pending_seconds)}</span>
        </>
      )}
      {data.auto_approved > 0 && (
        <>
          {' '}· {data.auto_approved} auto-approved by the step-down rule (not counted above)
        </>
      )}
    </p>
  );
}

// Stacked approved/rejected bars, one per day. Plain divs: two series and a
// few dozen bars don't justify a chart library.
function DailyChart({ daily }: { daily: Metrics['daily'] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...daily.map((d) => d.reviewed));
  const height = 160;
  const labelEvery = daily.length > 14 ? Math.ceil(daily.length / 7) : 1;
  const active = hover != null ? daily[hover] : null;

  return (
    <div className="mt-3">
      <div className="flex items-center gap-4 text-xs text-slate-400 mb-3" aria-hidden>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-accent" />Approved</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-slate-500" />Rejected</span>
        <span className="ml-auto text-slate-300 min-h-[1rem]">
          {active
            ? `${format(parseISO(active.date), 'EEE d MMM')}: ${active.approved} approved, ${active.rejected} rejected, ${active.edited} edited · median wait ${formatDuration(active.median_seconds_to_approve)}`
            : `Peak ${max} in a day`}
        </span>
      </div>
      <div
        className="flex items-end gap-[2px] border-b border-slate-700"
        style={{ height }}
        role="img"
        aria-label="Approved and rejected items per day. The table below has the same numbers."
        onMouseLeave={() => setHover(null)}
      >
        {daily.map((d, i) => (
          <div
            key={d.date}
            className={clsx('flex-1 h-full flex flex-col justify-end items-center rounded-sm', hover === i && 'bg-slate-700/40')}
            onMouseEnter={() => setHover(i)}
          >
            {d.rejected > 0 && (
              <div
                className="w-full max-w-[36px] bg-slate-500 rounded-t-[3px] mb-[2px]"
                style={{ height: (d.rejected / max) * (height - 8) }}
              />
            )}
            {d.approved > 0 && (
              <div
                className={clsx('w-full max-w-[36px] bg-accent', d.rejected === 0 && 'rounded-t-[3px]')}
                style={{ height: (d.approved / max) * (height - 8) }}
              />
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-[2px] mt-1.5">
        {daily.map((d, i) => (
          <div key={d.date} className="flex-1 text-center text-[10px] text-slate-500 tabular-nums">
            {i % labelEvery === 0 ? format(parseISO(d.date), daily.length > 14 ? 'd MMM' : 'EEE') : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

function BucketTable({
  rows,
}: {
  rows: { key: string; label: string; bucket: ReviewMetricsBucket }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
            <th className="font-medium px-5 py-2"></th>
            <th className="font-medium px-3 py-2 text-right">Reviewed</th>
            <th className="font-medium px-3 py-2 text-right">Approval rate</th>
            <th className="font-medium px-3 py-2 text-right">Edits per item</th>
            <th className="font-medium px-5 py-2 text-right">Median time to approve</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, bucket: b }) => (
            <tr key={key} className="border-b border-slate-800 last:border-0 text-slate-200 tabular-nums">
              <td className="px-5 py-2 whitespace-nowrap">{label}</td>
              <td className="px-3 py-2 text-right">{b.reviewed}</td>
              <td className="px-3 py-2 text-right">{pct(b.approval_rate)}</td>
              <td className="px-3 py-2 text-right">{ratio(b.edits_per_item)}</td>
              <td className="px-5 py-2 text-right">{formatDuration(b.median_seconds_to_approve)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
