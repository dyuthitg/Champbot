// What's actually happening behind the scenes, in plain terms.
//
// "Agent" is our internal word for a piece of the automation; nobody using
// this screen should have to learn it. Every card leads with what that part
// does for you, not with its internal name -- and three numbers up top
// answer the one question that actually matters: is everything okay right
// now, or does something need me?

import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import gsap from 'gsap';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  MessageSquare,
  Shield,
  ShieldCheck,
  UserCheck,
  Zap,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import { useGeneralWebSocket } from '@/hooks/useWebSocket';
import type { Agent, AgentStatus } from '@/types';
import { clsx } from 'clsx';
import { formatDistanceToNow } from 'date-fns';

const AGENT_ICON: Record<Agent['type'], typeof Zap> = {
  account_manager: UserCheck,
  content_analysis: Eye,
  interaction: Zap,
  conversation: MessageSquare,
  safety: Shield,
};

// A distinct color per part -- purely so five cards in a grid read as five
// different things at a glance, the way the old dashboard's gradients did,
// just calmer.
const AGENT_TINT: Record<Agent['type'], string> = {
  account_manager: 'from-blue-500/20 to-blue-600/5 text-blue-300',
  content_analysis: 'from-purple-500/20 to-purple-600/5 text-purple-300',
  interaction: 'from-emerald-500/20 to-emerald-600/5 text-emerald-300',
  conversation: 'from-orange-500/20 to-orange-600/5 text-orange-300',
  safety: 'from-red-500/20 to-red-600/5 text-red-300',
};

// What each part actually does, in words a non-technical owner would use --
// the API only gives us a short internal name ("Content Analysis").
const AGENT_DESCRIPTION: Record<Agent['type'], string> = {
  account_manager: 'Keeps your connected LinkedIn accounts logged in and healthy.',
  content_analysis: "Reads people's profiles and posts to judge who's worth reaching out to.",
  interaction: 'Sends the likes, connection requests, and comments on your behalf.',
  conversation: 'Writes and sends replies in your conversations.',
  safety: 'Watches everything else and slows down the moment something looks risky.',
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: 'Idle',
  processing: 'Working',
  waiting: 'Waiting',
  error: 'Needs attention',
};

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function AgentMonitor() {
  const containerRef = useRef<HTMLDivElement>(null);
  const hasEnteredRef = useRef(false);

  const { isConnected } = useGeneralWebSocket();

  const { data: agents, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: agentApi.list,
    refetchInterval: 3000,
  });

  // GSAP: reveal the cards once on mount, never on a routine poll. `agents`
  // is a fresh array reference every 3 seconds even when nothing changed,
  // and re-running this per poll used to tear down and restart the
  // animation mid-flight, sometimes latching a card's opacity at 0 for
  // good (Week 1 audit). A ref that's only set true once is what actually
  // fixes that -- reduced motion was a separate, real bug hiding behind it.
  useEffect(() => {
    if (!containerRef.current || !agents || hasEnteredRef.current) return;
    hasEnteredRef.current = true;
    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline();
      tl.from('.monitor-header', { y: -20, opacity: 0, duration: 0.5, ease: 'power3.out' });
      tl.from(
        '.stat-tile',
        { y: 16, opacity: 0, stagger: 0.06, duration: 0.35, ease: 'power2.out' },
        '-=0.25',
      );
      tl.from(
        '.agent-card',
        { y: 24, opacity: 0, stagger: 0.07, duration: 0.4, ease: 'power2.out' },
        '-=0.2',
      );
    }, containerRef);

    return () => ctx.revert();
  }, [agents]);

  const working = (agents ?? []).filter((a) => a.status === 'processing').length;
  const needsAttention = (agents ?? []).filter((a) => a.status === 'error').length;
  const completedTotal = (agents ?? []).reduce((sum, a) => sum + a.tasks_completed, 0);
  const reduced = prefersReducedMotion();

  if (isLoading) return <LoadingState />;

  return (
    <div ref={containerRef} className="max-w-6xl mx-auto px-4 py-8">
      <div className="monitor-header flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Automation activity</h1>
          <p className="text-slate-400 mt-1">
            What your automation is doing right now, live.
          </p>
        </div>
        {isConnected && (
          <span className="inline-flex items-center gap-1.5 text-sm text-success-fg mt-1">
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

      {/* Three numbers, not five -- the ones an owner actually cares about. */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <StatTile
          label="Working right now"
          value={working}
          icon={<Zap size={18} />}
          tone={working > 0 ? 'accent' : 'neutral'}
        />
        <StatTile
          label="Completed"
          value={completedTotal}
          icon={<CheckCircle2 size={18} />}
          tone="success"
        />
        <StatTile
          label="Needs attention"
          value={needsAttention}
          icon={<AlertTriangle size={18} />}
          tone={needsAttention > 0 ? 'danger' : 'neutral'}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(agents ?? []).map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>

      {!isLoading && (agents ?? []).length === 0 && (
        <div className="text-center py-16">
          <ShieldCheck className="mx-auto text-slate-600 mb-4" size={40} />
          <h2 className="text-lg font-semibold text-slate-200">Nothing to show yet</h2>
          <p className="text-slate-400 mt-2">
            Once your automation starts running, its activity shows up here.
          </p>
        </div>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone: 'accent' | 'success' | 'danger' | 'neutral';
}) {
  const toneClasses = {
    accent: 'text-purple-300 bg-accent/15',
    success: 'text-success-fg bg-success/15',
    danger: 'text-danger-fg bg-danger/15',
    neutral: 'text-slate-400 bg-slate-700/50',
  }[tone];

  return (
    <div className="stat-tile rounded-xl bg-slate-800/60 border border-slate-700 p-4 flex items-center gap-3">
      <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center shrink-0', toneClasses)}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold text-slate-100 leading-none">
          {value.toLocaleString()}
        </div>
        <div className="text-xs text-slate-400 mt-1">{label}</div>
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  const Icon = AGENT_ICON[agent.type] ?? Zap;
  const description = AGENT_DESCRIPTION[agent.type];
  const tint = AGENT_TINT[agent.type] ?? 'from-slate-500/20 to-slate-600/5 text-slate-300';
  const reduced = prefersReducedMotion();

  return (
    <motion.div
      layout
      whileHover={reduced ? undefined : { y: -2 }}
      transition={{ type: 'spring', stiffness: 300 }}
      className={clsx(
        'agent-card rounded-xl border p-4 sm:p-5 bg-slate-800/60',
        agent.status === 'error'
          ? 'border-danger/40'
          : agent.status === 'processing'
            ? 'border-accent/40'
            : 'border-slate-700',
      )}
    >
      <div className="flex items-start gap-3 sm:gap-4">
        <div
          className={clsx(
            'w-11 h-11 rounded-xl shrink-0 flex items-center justify-center bg-gradient-to-br',
            tint,
          )}
        >
          <Icon size={20} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold text-slate-100">{agent.name}</h3>
            <StatusBadge status={agent.status} />
          </div>
          <p className="text-sm text-slate-400 mt-1 leading-snug">{description}</p>

          {agent.current_task && agent.status === 'processing' && (
            <p className="text-sm text-purple-200 mt-2.5 bg-accent/10 border border-accent/20 rounded-lg px-2.5 py-1.5">
              <span className="text-purple-300/70">Right now: </span>
              {agent.current_task}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 pt-3 border-t border-slate-700/60 text-xs text-slate-500">
            <span>
              <span className="text-slate-300 font-medium">{agent.tasks_completed}</span>{' '}
              completed
            </span>
            {agent.tasks_failed > 0 && (
              <span className="text-danger-fg">
                <span className="font-medium">{agent.tasks_failed}</span> needed attention
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <Clock size={12} />
              {formatDistanceToNow(new Date(agent.last_activity), { addSuffix: true })}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatusBadge({ status }: { status: AgentStatus }) {
  const reduced = prefersReducedMotion();
  const tone = {
    idle: 'bg-slate-700/50 text-slate-400',
    processing: 'bg-accent/15 text-purple-300',
    waiting: 'bg-warn/15 text-warn',
    error: 'bg-danger/10 text-danger-fg',
  }[status];
  const dot = {
    idle: 'bg-slate-500',
    processing: 'bg-accent',
    waiting: 'bg-warn',
    error: 'bg-danger',
  }[status];

  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium', tone)}>
      <motion.span
        className={clsx('w-1.5 h-1.5 rounded-full', dot)}
        animate={
          status === 'processing' && !reduced
            ? { opacity: [1, 0.35, 1], transition: { duration: 1.5, repeat: Infinity } }
            : {}
        }
      />
      {STATUS_LABEL[status]}
    </span>
  );
}

function LoadingState() {
  const reduced = prefersReducedMotion();
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <motion.div
          animate={reduced ? undefined : { rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          className="inline-block text-accent"
        >
          <Zap size={40} />
        </motion.div>
        <p className="mt-4 text-slate-400">Checking on your automation...</p>
      </div>
    </div>
  );
}
