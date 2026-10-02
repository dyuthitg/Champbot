// Connect and manage the LinkedIn identities the system acts as.
//
// The connect flow asks for a session cookie rather than a password on
// purpose, and the UI says so — storing someone's LinkedIn password would make
// this a credential honeypot, while a cookie can be revoked by signing out.

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  CheckCircle2,
  Globe,
  HelpCircle,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  KeyRound,
  Trash2,
} from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, targetingApi } from '@/lib/api';
import type { AccountStatus, ConnectedAccount } from '@/types';

const STATUS_TONE: Record<AccountStatus, string> = {
  active: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  inactive: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  suspended: 'bg-red-500/15 text-red-300 border-red-500/30',
  rate_limited: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  auth_required: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  error: 'bg-red-500/15 text-red-300 border-red-500/30',
};

const STATUS_LABEL: Record<AccountStatus, string> = {
  active: 'Connected',
  inactive: 'Disconnected',
  suspended: 'Suspended',
  rate_limited: 'Paused — LinkedIn pushed back',
  auth_required: 'Session expired — needs a new cookie',
  error: 'Error',
};

const PROXY_HINT =
  'Use a sticky address that stays the same: for DataImpulse, a port from 10000 up ' +
  '(a different one per account), not 823. A proxy that changes address gets the ' +
  'account signed out. We test it before saving.';

export function Accounts() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });
  const { data: icps = [] } = useQuery({
    queryKey: ['icps'],
    queryFn: targetingApi.listIcps,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['accounts'] });

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-100">LinkedIn Accounts</h1>
          <p className="text-slate-400 mt-1">
            The LinkedIn identities this system acts as.
          </p>
        </div>
        <button onClick={() => setShowForm((v) => !v)} className="btn-primary shrink-0">
          <Plus size={16} />
          Connect account
        </button>
      </header>

      {error && (
        <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/40 text-red-200 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {showForm && (
        <ConnectForm
          onDone={() => {
            setShowForm(false);
            refresh();
          }}
          onError={setError}
        />
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 className="animate-spin" />
        </div>
      ) : accounts.length === 0 && !showForm ? (
        <div className="text-center py-16">
          <ShieldCheck className="mx-auto text-slate-600 mb-4" size={40} />
          <h2 className="text-lg font-semibold text-slate-200">No accounts connected</h2>
          <p className="text-slate-400 mt-2">
            Connect a LinkedIn account to start suggesting outreach.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {accounts.map((account) => (
            <AccountRow
              key={account.id}
              account={account}
              icps={icps}
              onChanged={refresh}
              onError={setError}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectForm({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [liAt, setLiAt] = useState('');
  const [jsessionid, setJsessionid] = useState('');
  const [label, setLabel] = useState('');
  const [mode, setMode] = useState<'outreach' | 'account_based_engagement'>('outreach');
  const [proxyUrl, setProxyUrl] = useState('');
  const [showHelp, setShowHelp] = useState(false);

  const connect = useMutation({
    mutationFn: () =>
      accountApi.connect({
        li_at: liAt.trim(),
        jsessionid: jsessionid.trim() || undefined,
        label: label.trim() || undefined,
        mode,
        proxy_url: proxyUrl.trim() || undefined,
      }),
    onSuccess: (account) => {
      if (account.status !== 'active') {
        onError(
          'The account was saved, but LinkedIn rejected that session. Check the cookie values and try again.',
        );
      }
      onDone();
    },
    onError: (err: any) =>
      onError(err?.response?.data?.detail ?? 'Could not connect that account'),
  });

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      className="mb-6 rounded-xl bg-slate-800/60 border border-slate-700 p-5 overflow-hidden"
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-slate-100 font-semibold">Connect a LinkedIn account</h2>
          <p className="text-sm text-slate-400 mt-1">
            We ask for a session cookie, not your password — you can revoke it any
            time by signing out of LinkedIn.
          </p>
        </div>
        <button
          onClick={() => setShowHelp((v) => !v)}
          className="text-slate-400 hover:text-slate-200 shrink-0"
          title="How to find these values"
        >
          <HelpCircle size={18} />
        </button>
      </div>

      {showHelp && (
        <ol className="mb-4 text-sm text-slate-300 bg-slate-900/60 rounded-lg p-4 space-y-1.5 list-decimal list-inside">
          <li>Sign in to LinkedIn in your browser.</li>
          <li>
            Open developer tools → <span className="text-slate-100">Application</span> →{' '}
            <span className="text-slate-100">Cookies</span> → https://www.linkedin.com
          </li>
          <li>
            Copy the value of <code className="text-purple-300">li_at</code> and of{' '}
            <code className="text-purple-300">JSESSIONID</code> (drop the surrounding
            quotes).
          </li>
        </ol>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">li_at cookie (required)</span>
          <input
            type="password"
            value={liAt}
            onChange={(e) => setLiAt(e.target.value)}
            placeholder="AQEDAT…"
            className="input font-mono"
            autoComplete="off"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">
            JSESSIONID (needed to send anything)
          </span>
          <input
            type="password"
            value={jsessionid}
            onChange={(e) => setJsessionid(e.target.value)}
            placeholder="ajax:1234567890"
            className="input font-mono"
            autoComplete="off"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Label</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Dana — sales"
            className="input"
          />
        </label>

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">How should this account behave?</span>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
            className="select"
          >
            <option value="outreach">
              Outreach — meet new people who match the target profile
            </option>
            <option value="account_based_engagement">
              Engagement — build presence with people already in the network
            </option>
          </select>
        </label>

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">Proxy (recommended)</span>
          <input
            type="password"
            value={proxyUrl}
            onChange={(e) => setProxyUrl(e.target.value)}
            placeholder="http://login__cr.in:password@gw.dataimpulse.com:10000"
            className="input font-mono"
            autoComplete="off"
          />
          <span className="text-xs text-slate-500">{PROXY_HINT}</span>
        </label>
      </div>

      <div className="flex items-center gap-3 mt-5 flex-wrap">
        <button
          onClick={() => connect.mutate()}
          disabled={connect.isPending || liAt.trim().length < 20}
          className="btn-primary shrink-0 whitespace-nowrap"
        >
          {connect.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <ShieldCheck size={16} />
          )}
          Connect &amp; verify
        </button>
        <span className="text-xs text-slate-500">
          New accounts start in warm-up: reduced volume for the first weeks.
        </span>
      </div>
    </motion.div>
  );
}

function AccountRow({
  account,
  icps,
  onChanged,
  onError,
}: {
  account: ConnectedAccount;
  icps: { id: string; name: string }[];
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [showCookie, setShowCookie] = useState(false);

  const verify = useMutation({
    mutationFn: () => accountApi.verify(account.id),
    onSuccess: (result) => {
      if (!result.ok) onError(result.error ?? 'That session is no longer valid.');
      onChanged();
    },
    onError: (err: any) =>
      onError(err?.response?.data?.detail ?? 'Could not verify that account'),
  });

  const update = useMutation({
    mutationFn: (payload: Parameters<typeof accountApi.update>[1]) =>
      accountApi.update(account.id, payload),
    onSuccess: onChanged,
  });

  const disconnect = useMutation({
    mutationFn: () => accountApi.disconnect(account.id),
    onSuccess: onChanged,
  });

  const caps = account.policy?.actions ?? {};

  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-slate-100 font-semibold truncate">
              {account.display_name ?? 'Unnamed account'}
            </h3>
            <span
              className={clsx(
                'px-2 py-0.5 rounded-full border text-xs font-medium',
                STATUS_TONE[account.status],
              )}
            >
              {account.status === 'active' ? (
                <CheckCircle2 size={11} className="inline mr-1 -mt-px" />
              ) : (
                <AlertTriangle size={11} className="inline mr-1 -mt-px" />
              )}
              {STATUS_LABEL[account.status]}
            </span>
            {account.policy?.warmup && (
              <span className="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-300 text-xs">
                warming up
              </span>
            )}
          </div>
          {account.headline && (
            <p className="text-sm text-slate-400 mt-0.5 truncate">{account.headline}</p>
          )}
          {account.transport && (
            <p className="text-xs text-slate-500 mt-1">
              Verified via the {account.transport} transport
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => verify.mutate()}
            disabled={verify.isPending}
            className="btn-ghost"
            title="Re-check this session against LinkedIn"
          >
            {verify.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <RefreshCw size={15} />
            )}
            Verify
          </button>
          <button
            onClick={() => setShowCookie((v) => !v)}
            className={clsx(
              'btn-ghost',
              account.status === 'auth_required' && 'text-amber-300',
            )}
            title="Paste a fresh li_at cookie, keeping all settings"
          >
            <KeyRound size={15} />
            Update cookie
          </button>
          <button
            onClick={() => disconnect.mutate()}
            disabled={disconnect.isPending}
            className="btn-ghost text-red-400 hover:bg-red-500/10"
            title="Disconnect and delete stored credentials"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {showCookie && (
        <CookieUpdate
          account={account}
          onDone={() => {
            setShowCookie(false);
            onChanged();
          }}
          onCancel={() => setShowCookie(false)}
          onError={onError}
        />
      )}

      {/* Policy */}
      <div className="grid gap-4 sm:grid-cols-2 mt-4 pt-4 border-t border-slate-700">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Behaviour</span>
          <select
            value={account.mode ?? 'outreach'}
            onChange={(e) => update.mutate({ mode: e.target.value })}
            className="select"
          >
            <option value="outreach">Outreach — meet new people</option>
            <option value="account_based_engagement">
              Engagement — nurture existing network
            </option>
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">Target profile</span>
          <select
            value={account.active_icp_id ?? ''}
            onChange={(e) => update.mutate({ active_icp_id: e.target.value })}
            className="select"
          >
            <option value="">None selected</option>
            {icps.map((icp) => (
              <option key={icp.id} value={icp.id}>
                {icp.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ProxySetting account={account} onChanged={onChanged} onError={onError} />

      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-xs text-slate-400">
        <span>
          Invites{' '}
          <span className="text-slate-200">{caps.connect?.per_day ?? '—'}/day</span>
        </span>
        <span>
          Messages{' '}
          <span className="text-slate-200">{caps.message?.per_day ?? '—'}/day</span>
        </span>
        <span>
          Comments{' '}
          <span className="text-slate-200">{caps.comment?.per_day ?? '—'}/day</span>
        </span>
        <span>
          Active{' '}
          <span className="text-slate-200">
            {account.policy?.active_hours?.[0]}:00–{account.policy?.active_hours?.[1]}:00
          </span>
          {account.policy?.timezone && (
            <span className="text-slate-500"> {account.policy.timezone} time</span>
          )}
        </span>
        <span>
          Review queue{' '}
          <span className="text-slate-200">
            max {account.policy?.suggestion_budget ?? '—'}/day
          </span>
        </span>
      </div>
    </div>
  );
}

function ProxySetting({
  account,
  onChanged,
  onError,
}: {
  account: ConnectedAccount;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [proxyUrl, setProxyUrl] = useState('');
  const proxy = account.proxy;

  const save = useMutation({
    mutationFn: (url: string) => accountApi.update(account.id, { proxy_url: url }),
    onSuccess: () => {
      setEditing(false);
      setProxyUrl('');
      onChanged();
    },
    onError: (err: any) =>
      onError(err?.response?.data?.detail ?? 'Could not save that proxy'),
  });

  return (
    <div className="mt-4 pt-4 border-t border-slate-700 text-sm">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex items-center gap-2">
          <Globe size={15} className={proxy ? 'text-emerald-400' : 'text-amber-400'} />
          {proxy ? (
            <span className="text-slate-300 truncate">
              Proxy <span className="text-slate-100 font-mono">{proxy.host}</span>
              {proxy.ip && (
                <span className="text-slate-400">
                  {' '}· goes out as {proxy.ip}
                  {(proxy.city || proxy.country) &&
                    ` (${[proxy.city, proxy.country].filter(Boolean).join(', ')})`}
                </span>
              )}
            </span>
          ) : (
            <span className="text-amber-200">
              No proxy. LinkedIn sees the server's address, which can get this account
              signed out.
            </span>
          )}
        </div>
        {!editing && (
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={() => setEditing(true)} className="btn-ghost">
              {proxy ? 'Change' : 'Add proxy'}
            </button>
            {proxy && (
              <button
                onClick={() => save.mutate('')}
                disabled={save.isPending}
                className="btn-ghost text-slate-400"
              >
                Remove
              </button>
            )}
          </div>
        )}
      </div>

      {editing && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex gap-2 flex-wrap">
            <input
              type="password"
              value={proxyUrl}
              onChange={(e) => setProxyUrl(e.target.value)}
              placeholder="http://login__cr.in:password@gw.dataimpulse.com:10000"
              className="input font-mono flex-1 min-w-0"
              autoComplete="off"
              autoFocus
            />
            <button
              onClick={() => save.mutate(proxyUrl.trim())}
              disabled={save.isPending || !proxyUrl.trim()}
              className="btn-primary shrink-0"
            >
              {save.isPending && <Loader2 size={15} className="animate-spin" />}
              {save.isPending ? 'Testing…' : 'Test & save'}
            </button>
            <button onClick={() => setEditing(false)} className="btn-ghost shrink-0">
              Cancel
            </button>
          </div>
          <span className="text-xs text-slate-500">{PROXY_HINT}</span>
        </div>
      )}
    </div>
  );
}

function CookieUpdate({
  account,
  onDone,
  onCancel,
  onError,
}: {
  account: ConnectedAccount;
  onDone: () => void;
  onCancel: () => void;
  onError: (message: string) => void;
}) {
  const [liAt, setLiAt] = useState('');
  const [jsessionid, setJsessionid] = useState('');

  // Replaces only the session cookies; proxy, caps and warm-up progress stay.
  const save = useMutation({
    mutationFn: () =>
      accountApi.rotateCredentials(account.id, {
        li_at: liAt.trim(),
        jsessionid: jsessionid.trim() || undefined,
      }),
    onSuccess: (updated) => {
      if (updated.status !== 'active') {
        onError(
          'LinkedIn rejected that cookie. Copy li_at again from a browser where you are signed in.',
        );
      }
      onDone();
    },
    onError: (err: any) =>
      onError(err?.response?.data?.detail ?? 'Could not update the cookie'),
  });

  return (
    <div className="mt-4 pt-4 border-t border-slate-700">
      <p className="text-sm text-slate-300 mb-3">
        Paste fresh cookies from a browser signed in to LinkedIn. Settings, proxy and
        warm-up progress are kept.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">li_at cookie (required)</span>
          <input
            type="password"
            value={liAt}
            onChange={(e) => setLiAt(e.target.value)}
            placeholder="AQEDAT…"
            className="input font-mono"
            autoComplete="off"
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">JSESSIONID (needed to send anything)</span>
          <input
            type="password"
            value={jsessionid}
            onChange={(e) => setJsessionid(e.target.value)}
            placeholder="ajax:1234567890"
            className="input font-mono"
            autoComplete="off"
          />
        </label>
      </div>
      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || liAt.trim().length < 20}
          className="btn-primary"
        >
          {save.isPending ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <ShieldCheck size={15} />
          )}
          {save.isPending ? 'Checking…' : 'Save & verify'}
        </button>
        <button onClick={onCancel} className="btn-ghost">
          Cancel
        </button>
      </div>
    </div>
  );
}
