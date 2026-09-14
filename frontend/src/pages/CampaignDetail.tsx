// A single campaign, viewed on its own -- where clicking a card in the list,
// or finishing the create wizard, actually lands. Neither used to go
// anywhere real: both pointed at /campaigns/:id with no such route
// registered, so both silently fell through to the dashboard redirect.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Loader2,
  Pause,
  Play,
  Target,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { format } from 'date-fns';
import { accountApi, campaignApi } from '@/lib/api';
import { Button, Card, Chip, EmptyState } from '@/components/ui';
import type { CampaignStatus } from '@/types';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Same dot/border convention CampaignCard uses, so a campaign reads the
// same way whether you're looking at the list or this page.
const STATUS_DOT: Record<CampaignStatus, string> = {
  draft: 'bg-slate-400',
  scheduled: 'bg-purple-400',
  running: 'bg-accent',
  paused: 'bg-warn',
  completed: 'bg-success-fg',
  failed: 'bg-danger',
  cancelled: 'bg-slate-500',
};

const ACTION_LABELS: { key: 'like' | 'comment' | 'share' | 'follow'; label: string }[] = [
  { key: 'like', label: 'Like' },
  { key: 'comment', label: 'Comment' },
  { key: 'share', label: 'Share' },
  { key: 'follow', label: 'Follow' },
];

export function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reduced = prefersReducedMotion();

  const { data: campaign, isLoading, error } = useQuery({
    queryKey: ['campaign', id],
    queryFn: () => campaignApi.get(id!),
    enabled: !!id,
    retry: false,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });

  const startMutation = useMutation({
    mutationFn: () => campaignApi.start(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaign', id] });
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => campaignApi.pause(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaign', id] });
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-24 text-muted">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <EmptyState
        icon={<Target size={40} />}
        title="Campaign not found"
        body="It may have been deleted, or the link is out of date."
        cta={{ label: 'Back to Campaigns', href: '/campaigns' }}
      />
    );
  }

  const isRunning = campaign.status === 'running';
  const isBusy = startMutation.isPending || pauseMutation.isPending;
  const progressPercent =
    campaign.progress.total_tasks > 0
      ? Math.round((campaign.progress.completed_tasks / campaign.progress.total_tasks) * 100)
      : 0;
  const runningAccounts = accounts.filter((a) => campaign.account_ids.includes(a.id));

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate('/campaigns')}
        className="flex items-center gap-2 text-muted hover:text-foreground mb-4 min-h-[44px] sm:min-h-0"
      >
        <ArrowLeft size={18} />
        Back to Campaigns
      </button>

      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={clsx('w-2.5 h-2.5 rounded-full shrink-0', STATUS_DOT[campaign.status])} />
            <h1 className="text-2xl font-semibold text-slate-100 truncate">{campaign.name}</h1>
            <Chip tone="neutral" className="capitalize">{campaign.status}</Chip>
          </div>
          {campaign.description && (
            <p className="text-muted mt-2">{campaign.description}</p>
          )}
          <p className="text-xs text-muted mt-2 flex items-center gap-1">
            <Calendar size={12} />
            Created {format(new Date(campaign.created_at), 'MMM d, yyyy')}
          </p>
        </div>

        {(campaign.status === 'draft' || campaign.status === 'paused' || isRunning) && (
          <motion.div whileHover={reduced || isBusy ? undefined : { scale: 1.03 }} whileTap={reduced || isBusy ? undefined : { scale: 0.97 }}>
            <Button
              variant={isRunning ? 'ghost' : 'success'}
              icon={
                isBusy ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : isRunning ? (
                  <Pause size={15} />
                ) : (
                  <Play size={15} />
                )
              }
              disabled={isBusy}
              onClick={() => (isRunning ? pauseMutation.mutate() : startMutation.mutate())}
              className="shrink-0 whitespace-nowrap"
            >
              {isRunning ? 'Pause campaign' : 'Start campaign'}
            </Button>
          </motion.div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3 mb-6">
        <Card className="text-center">
          <div className="text-2xl font-semibold text-foreground">{campaign.progress.total_tasks}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Total</div>
        </Card>
        <Card className="text-center">
          <div className="text-2xl font-semibold text-success-fg">{campaign.progress.completed_tasks}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Completed</div>
        </Card>
        <Card className="text-center">
          <div className="text-2xl font-semibold text-danger-fg">{campaign.progress.failed_tasks}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Failed</div>
        </Card>
      </div>

      <Card className="mb-6">
        <div className="flex items-center justify-between text-sm mb-2">
          <span className="font-medium text-foreground">Progress</span>
          <span className="text-muted">{progressPercent}%</span>
        </div>
        <div className="h-2 bg-slate-900/70 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-accent to-purple-600"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </Card>

      <Card className="mb-6">
        <h2 className="text-sm font-semibold text-foreground mb-3">Actions</h2>
        <div className="flex flex-wrap gap-2">
          {ACTION_LABELS.map(({ key, label }) => (
            <Chip key={key} tone={campaign.actions[key] ? 'accent' : 'neutral'}>
              {campaign.actions[key] ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
              {label}
            </Chip>
          ))}
        </div>
      </Card>

      <Card className="mb-6">
        <h2 className="text-sm font-semibold text-foreground mb-3">
          Running on
        </h2>
        {runningAccounts.length === 0 ? (
          <p className="text-sm text-muted">
            {campaign.account_ids.length === 0
              ? 'No account attached to this campaign.'
              : "The account this campaign was created with is no longer connected."}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {runningAccounts.map((a) => (
              <Chip key={a.id} tone="neutral">{a.display_name ?? 'Unnamed account'}</Chip>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-foreground mb-3">
          Target URLs ({campaign.target_urls.length})
        </h2>
        {campaign.target_urls.length === 0 ? (
          <p className="text-sm text-muted">No target URLs added.</p>
        ) : (
          <ul className="space-y-1.5 max-h-64 overflow-y-auto">
            {campaign.target_urls.map((url) => (
              <li key={url} className="text-sm text-slate-300 truncate">
                <a href={url} target="_blank" rel="noreferrer" className="hover:underline hover:text-foreground">
                  {url}
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
