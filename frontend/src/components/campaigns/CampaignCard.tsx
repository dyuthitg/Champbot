import { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Play,
  Pause,
  Calendar,
  Target,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import { format } from 'date-fns';
import type { Campaign } from '@/types';
import { campaignApi } from '@/lib/api';
import { clsx } from 'clsx';

interface CampaignCardProps {
  campaign: Campaign;
}

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Dot + border colour per status. Text always renders on the dark card
// surface, never inside a light chip, so every entry needs only the two
// colours that actually get used below.
const statusConfig = {
  draft: { dot: 'bg-slate-400', border: 'border-border' },
  scheduled: { dot: 'bg-purple-400', border: 'border-purple-500/40' },
  running: { dot: 'bg-accent', border: 'border-accent/50' },
  paused: { dot: 'bg-warn', border: 'border-warn/40' },
  completed: { dot: 'bg-success-fg', border: 'border-success/40' },
  failed: { dot: 'bg-danger', border: 'border-danger/40' },
  cancelled: { dot: 'bg-slate-500', border: 'border-border' },
};

// forwardRef because AnimatePresence's popLayout exit animation clones this
// component's direct child and attaches a ref to it for measurement -- a
// plain function component can't take one, which surfaced as a silent
// "Function components cannot be given refs" console warning (exit
// animations for removed cards likely weren't measuring correctly).
export const CampaignCard = forwardRef<HTMLDivElement, CampaignCardProps>(function CampaignCard(
  { campaign },
  ref,
) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reduced = prefersReducedMotion();

  const startMutation = useMutation({
    mutationFn: () => campaignApi.start(campaign.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => campaignApi.pause(campaign.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });

  const progress =
    campaign.progress.total_tasks > 0
      ? (campaign.progress.completed_tasks / campaign.progress.total_tasks) * 100
      : 0;

  const isRunning = campaign.status === 'running';
  const config = statusConfig[campaign.status];
  const isLoading = startMutation.isPending || pauseMutation.isPending;

  const handleAction = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isRunning) {
      pauseMutation.mutate();
    } else if (campaign.status === 'draft' || campaign.status === 'paused') {
      startMutation.mutate();
    }
  };

  return (
    <motion.div
      ref={ref}
      layout
      layoutId={`campaign-${campaign.id}`}
      initial={reduced ? undefined : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, scale: 0.9 }}
      whileHover={reduced ? undefined : { scale: 1.01 }}
      whileTap={reduced ? undefined : { scale: 0.98 }}
      onClick={() => navigate(`/campaigns/${campaign.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          navigate(`/campaigns/${campaign.id}`);
        }
      }}
      className={clsx(
        'bg-surface rounded-xl p-6 cursor-pointer border transition-colors',
        config.border
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        {/* Status Badge */}
        <motion.div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium bg-slate-900/60 text-foreground"
          animate={
            isRunning && !reduced
              ? { scale: [1, 1.05, 1], transition: { duration: 2, repeat: Infinity } }
              : {}
          }
        >
          <motion.span
            className={clsx('w-2 h-2 rounded-full', config.dot)}
            animate={
              isRunning && !reduced
                ? { opacity: [1, 0.3, 1], transition: { duration: 1.5, repeat: Infinity } }
                : {}
            }
          />
          <span className="capitalize">{campaign.status}</span>
        </motion.div>

        {/* Date */}
        <div className="flex items-center gap-1 text-sm text-muted">
          <Calendar size={14} />
          <span>{format(new Date(campaign.created_at), 'MMM d, yyyy')}</span>
        </div>
      </div>

      {/* Campaign Info */}
      <h3 className="text-lg font-semibold text-foreground mb-2 line-clamp-1">
        {campaign.name}
      </h3>
      <p className="text-muted text-sm mb-4 line-clamp-2">
        {campaign.description}
      </p>

      {/* Actions Summary */}
      <div className="flex flex-wrap gap-2 mb-4">
        {campaign.actions.like && (
          <span className="px-2 py-1 bg-slate-900/60 text-slate-300 rounded text-xs font-medium">
            👍 Like
          </span>
        )}
        {campaign.actions.comment && (
          <span className="px-2 py-1 bg-slate-900/60 text-slate-300 rounded text-xs font-medium">
            💬 Comment
          </span>
        )}
        {campaign.actions.share && (
          <span className="px-2 py-1 bg-slate-900/60 text-slate-300 rounded text-xs font-medium">
            🔄 Share
          </span>
        )}
        {campaign.actions.follow && (
          <span className="px-2 py-1 bg-slate-900/60 text-slate-300 rounded text-xs font-medium">
            ➕ Follow
          </span>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-2">
          <span className="font-medium text-muted">Progress</span>
          <motion.span
            key={progress}
            initial={reduced ? undefined : { scale: 1.2 }}
            animate={{ scale: 1 }}
            transition={{ duration: 0.3 }}
            className="font-semibold text-foreground"
          >
            {Math.round(progress)}%
          </motion.span>
        </div>

        <div className="h-2 bg-slate-900/70 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-accent to-purple-600"
            initial={reduced ? { width: `${progress}%` } : { width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={reduced ? { duration: 0 } : { duration: 1, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-4">
        <StatItem
          icon={<Target size={16} />}
          label="Total"
          value={campaign.progress.total_tasks}
          delay={0.1}
          color="text-foreground"
          reduced={reduced}
        />
        <StatItem
          icon={<CheckCircle2 size={16} />}
          label="Done"
          value={campaign.progress.completed_tasks}
          delay={0.2}
          color="text-success-fg"
          reduced={reduced}
        />
        <StatItem
          icon={<XCircle size={16} />}
          label="Failed"
          value={campaign.progress.failed_tasks}
          delay={0.3}
          color="text-danger-fg"
          reduced={reduced}
        />
      </div>

      {/* Action Button */}
      <motion.button
        whileHover={reduced || isLoading ? undefined : { scale: 1.02 }}
        whileTap={reduced || isLoading ? undefined : { scale: 0.98 }}
        onClick={handleAction}
        disabled={isLoading || campaign.status === 'completed'}
        className={clsx(
          'w-full min-h-[44px] sm:min-h-0 py-2 px-4 rounded-lg font-medium text-white',
          'transition-colors duration-200',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          'flex items-center justify-center gap-2',
          isRunning
            ? 'bg-warn hover:bg-warn/85'
            : campaign.status === 'completed'
            ? 'bg-slate-600'
            : 'bg-success hover:bg-success/85'
        )}
      >
        {isLoading ? (
          <>
            <motion.div
              animate={reduced ? undefined : { rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            >
              <Loader2 size={18} />
            </motion.div>
            <span>Processing...</span>
          </>
        ) : isRunning ? (
          <>
            <Pause size={18} />
            <span>Pause Campaign</span>
          </>
        ) : campaign.status === 'completed' ? (
          <>
            <CheckCircle2 size={18} />
            <span>Completed</span>
          </>
        ) : (
          <>
            <Play size={18} />
            <span>Start Campaign</span>
          </>
        )}
      </motion.button>
    </motion.div>
  );
});

CampaignCard.displayName = 'CampaignCard';

interface StatItemProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  delay?: number;
  color?: string;
  reduced?: boolean;
}

function StatItem({ icon, label, value, delay = 0, color = 'text-foreground', reduced }: StatItemProps) {
  return (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: reduced ? 0 : delay }}
      className="text-center"
    >
      <div className="flex items-center justify-center gap-1 text-muted mb-1">
        {icon}
        <p className="text-xs">{label}</p>
      </div>
      <motion.p
        className={clsx('text-2xl font-bold', color)}
        initial={reduced ? undefined : { scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 200, delay: reduced ? 0 : delay + 0.1 }}
      >
        {value}
      </motion.p>
    </motion.div>
  );
}
