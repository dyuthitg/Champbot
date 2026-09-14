import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import gsap from 'gsap';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Shield,
  MessageSquare,
  Eye,
  UserCheck,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import { useGeneralWebSocket } from '@/hooks/useWebSocket';
import type { Agent, AgentStatus } from '@/types';
import { clsx } from 'clsx';
import { formatDistanceToNow } from 'date-fns';

const agentIcons = {
  account_manager: UserCheck,
  content_analysis: Eye,
  interaction: Zap,
  conversation: MessageSquare,
  safety: Shield,
};

const agentColors = {
  account_manager: 'from-blue-500 to-blue-600',
  content_analysis: 'from-purple-500 to-purple-600',
  interaction: 'from-green-500 to-green-600',
  conversation: 'from-orange-500 to-orange-600',
  safety: 'from-red-500 to-red-600',
};

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function AgentMonitor() {
  const containerRef = useRef<HTMLDivElement>(null);
  const hasEnteredRef = useRef(false);

  // Connect to WebSocket for real-time updates
  const { isConnected, lastMessage } = useGeneralWebSocket();

  // Fetch agents
  const { data: agents, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: agentApi.list,
    refetchInterval: 3000, // Refetch every 3 seconds
  });

  // GSAP: Animate page entry, exactly once -- skipped outright when the
  // visitor's OS says reduce motion, rather than played at a shorter
  // duration. A entrance animation isn't required to understand this
  // screen, so the honest fix is "doesn't run," not "runs faster."
  //
  // `agents` is a fresh array reference on every 3-second poll even when
  // nothing changed, and this used to depend on `agents` directly: every
  // poll tore down the previous timeline and started a new one from
  // opacity 0. Two polls landing close together could revert the first
  // tween mid-flight and leave a card's opacity latched at 0 forever --
  // the "renders a blank screen" finding in the Week 1 audit. Running once
  // per mount (guarded by a ref, not a dependency the poll churns) is the
  // actual fix; reduced motion was a separate, real bug hiding behind it.
  useEffect(() => {
    if (!containerRef.current || !agents || hasEnteredRef.current) return;
    hasEnteredRef.current = true;
    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline();

      // Animate header
      tl.from('.monitor-header', {
        y: -30,
        opacity: 0,
        duration: 0.6,
        ease: 'power3.out',
      });

      // Stagger animate agent cards
      tl.from(
        '.agent-card',
        {
          y: 50,
          opacity: 0,
          stagger: 0.1,
          duration: 0.5,
          ease: 'power2.out',
        },
        '-=0.3'
      );

      // Animate stats cards
      tl.from(
        '.stat-card',
        {
          scale: 0.8,
          opacity: 0,
          stagger: 0.1,
          duration: 0.4,
        },
        '-=0.3'
      );
    }, containerRef);

    return () => ctx.revert();
  }, [agents]);

  // Pulse animation for processing agents. Keyed on *which* agents are
  // processing (a stable, comma-joined id string), not on the `agents`
  // array reference -- so a poll that changes nothing doesn't restart the
  // glow, but an agent actually entering/leaving "processing" does.
  const processingKey = (agents ?? [])
    .filter((a) => a.status === 'processing')
    .map((a) => a.id)
    .join(',');

  useEffect(() => {
    if (!containerRef.current || !processingKey || prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      gsap.to('.agent-card.processing', {
        boxShadow: '0 0 25px rgba(168, 85, 247, 0.35)',
        duration: 1.5,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
    }, containerRef);

    return () => ctx.revert();
  }, [processingKey]);

  // Calculate stats
  const stats = agents
    ? {
        total: agents.length,
        active: agents.filter((a) => a.status === 'processing').length,
        idle: agents.filter((a) => a.status === 'idle').length,
        totalCompleted: agents.reduce((sum, a) => sum + a.tasks_completed, 0),
        totalFailed: agents.reduce((sum, a) => sum + a.tasks_failed, 0),
      }
    : null;

  if (isLoading) {
    return <LoadingState />;
  }

  return (
    <div ref={containerRef} className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="monitor-header mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-100 mb-2">
              Agent Activity Monitor
            </h1>
            <p className="text-muted">
              Real-time status of all automation agents
              {isConnected && (
                <span className="ml-2 inline-flex items-center gap-1 text-sm text-success-fg">
                  <motion.span
                    className="w-2 h-2 bg-success-fg rounded-full"
                    animate={
                      prefersReducedMotion()
                        ? undefined
                        : {
                            opacity: [1, 0.3, 1],
                            transition: { duration: 2, repeat: Infinity },
                          }
                    }
                  />
                  Live
                </span>
              )}
            </p>
          </div>

          <motion.div
            animate={prefersReducedMotion() ? undefined : { rotate: 360 }}
            transition={{ duration: 10, repeat: Infinity, ease: 'linear' }}
            className="text-accent"
          >
            <Activity size={40} />
          </motion.div>
        </div>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatsCard
              label="Total Agents"
              value={stats.total}
              icon={<Activity size={20} />}
              color="text-foreground"
            />
            <StatsCard
              label="Active"
              value={stats.active}
              icon={<Zap size={20} />}
              color="text-accent"
            />
            <StatsCard
              label="Idle"
              value={stats.idle}
              icon={<Clock size={20} />}
              color="text-muted"
            />
            <StatsCard
              label="Completed"
              value={stats.totalCompleted}
              icon={<CheckCircle2 size={20} />}
              color="text-success-fg"
            />
            <StatsCard
              label="Failed"
              value={stats.totalFailed}
              icon={<XCircle size={20} />}
              color="text-danger-fg"
            />
          </div>
        )}
      </div>

      {/* Agent Cards */}
      <div className="space-y-4">
        {agents?.map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>

      {/* Message Flow Visualization */}
      {lastMessage && (
        <MessageNotification message={lastMessage.type} />
      )}
    </div>
  );
}

interface StatsCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}

function StatsCard({ label, value, icon, color }: StatsCardProps) {
  const reduced = prefersReducedMotion();
  return (
    <motion.div
      className="stat-card bg-surface border border-border rounded-lg p-4"
      whileHover={reduced ? undefined : { scale: 1.05, y: -5 }}
      transition={{ type: 'spring', stiffness: 300 }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-muted">{label}</span>
        <span className={color}>{icon}</span>
      </div>
      <motion.p
        className={clsx('text-2xl font-semibold', color)}
        initial={reduced ? undefined : { scale: 0 }}
        animate={reduced ? undefined : { scale: 1 }}
        transition={{ type: 'spring', stiffness: 200, delay: 0.1 }}
      >
        {value}
      </motion.p>
    </motion.div>
  );
}

interface AgentCardProps {
  agent: Agent;
}

function AgentCard({ agent }: AgentCardProps) {
  const Icon = agentIcons[agent.type];
  const gradientColor = agentColors[agent.type];
  const reduced = prefersReducedMotion();

  return (
    <motion.div
      layout
      className={clsx(
        'agent-card bg-surface rounded-xl p-4 sm:p-6 border',
        agent.status === 'processing' ? 'processing border-accent/50' : 'border-border'
      )}
      whileHover={reduced ? undefined : { scale: 1.01 }}
      transition={{ type: 'spring', stiffness: 300 }}
    >
      <div className="flex items-start gap-4 sm:gap-6">
        {/* Agent Icon */}
        <motion.div
          className={clsx(
            'w-12 h-12 sm:w-16 sm:h-16 rounded-xl bg-gradient-to-br shrink-0',
            gradientColor,
            'flex items-center justify-center text-white'
          )}
          animate={
            agent.status === 'processing' && !reduced
              ? {
                  rotate: [0, 5, -5, 0],
                  transition: { duration: 2, repeat: Infinity },
                }
              : {}
          }
        >
          <Icon size={28} />
        </motion.div>

        {/* Agent Info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <h3 className="text-lg font-semibold text-foreground truncate">{agent.name}</h3>
            <StatusBadge status={agent.status} />
          </div>

          {agent.current_task && (
            <div className="mb-4">
              <p className="text-sm text-muted">Current Task:</p>
              <p className="text-sm font-medium text-foreground">
                {agent.current_task}
              </p>
            </div>
          )}

          {/* Progress Bar (if processing) */}
          {agent.status === 'processing' && (
            <div className="mb-4">
              <div className="h-2 bg-slate-900/70 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-accent to-purple-600"
                  initial={reduced ? undefined : { width: '0%' }}
                  animate={reduced ? { width: '100%' } : { width: '100%' }}
                  transition={
                    reduced ? { duration: 0 } : { duration: 3, repeat: Infinity, ease: 'linear' }
                  }
                />
              </div>
            </div>
          )}

          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-4">
            <div>
              <p className="text-xs text-muted">Completed</p>
              <p className="text-lg font-bold text-success-fg">
                {agent.tasks_completed}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Failed</p>
              <p className="text-lg font-bold text-danger-fg">
                {agent.tasks_failed}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Last Active</p>
              <p className="text-lg font-bold text-foreground">
                {formatDistanceToNow(new Date(agent.last_activity), {
                  addSuffix: true,
                })}
              </p>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatusBadge({ status }: { status: AgentStatus }) {
  const reduced = prefersReducedMotion();
  const config = {
    idle: {
      bg: 'bg-slate-700/50',
      text: 'text-muted',
      dot: 'bg-slate-400',
    },
    processing: {
      bg: 'bg-accent/15',
      text: 'text-purple-300',
      dot: 'bg-accent',
    },
    waiting: {
      bg: 'bg-warn/15',
      text: 'text-warn',
      dot: 'bg-warn',
    },
    error: {
      bg: 'bg-danger/10',
      text: 'text-danger-fg',
      dot: 'bg-danger',
    },
  };

  const { bg, text, dot } = config[status];

  return (
    <motion.div
      className={clsx(
        'inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium',
        bg,
        text
      )}
      animate={
        status === 'processing' && !reduced
          ? {
              scale: [1, 1.05, 1],
              transition: { duration: 2, repeat: Infinity },
            }
          : {}
      }
    >
      <motion.span
        className={clsx('w-2 h-2 rounded-full', dot)}
        animate={
          status === 'processing' && !reduced
            ? {
                opacity: [1, 0.3, 1],
                transition: { duration: 1.5, repeat: Infinity },
              }
            : {}
        }
      />
      <span className="capitalize">{status}</span>
    </motion.div>
  );
}

function MessageNotification({ message }: { message: string }) {
  const reduced = prefersReducedMotion();
  return (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, y: 50 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, y: -50 }}
      className="fixed bottom-4 right-4 bg-accent text-white px-6 py-3 rounded-lg shadow-lg"
    >
      <p className="text-sm font-medium">{message}</p>
    </motion.div>
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
          className="inline-block"
        >
          <Activity size={48} className="text-accent" />
        </motion.div>
        <p className="mt-4 text-muted">Loading agent activity...</p>
      </div>
    </div>
  );
}
