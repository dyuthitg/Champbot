import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { Plus, Search, Loader2 } from 'lucide-react';
import { CampaignCard } from '@/components/campaigns/CampaignCard';
import { campaignApi } from '@/lib/api';
import { useGeneralWebSocket } from '@/hooks/useWebSocket';
import type { CampaignStatus } from '@/types';
import { clsx } from 'clsx';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const statusFilters: { label: string; value: CampaignStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Running', value: 'running' },
  { label: 'Draft', value: 'draft' },
  { label: 'Paused', value: 'paused' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
];

export function CampaignList() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [statusFilter, setStatusFilter] = useState<CampaignStatus | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Connect to WebSocket for real-time updates
  const { isConnected } = useGeneralWebSocket();

  // Fetch campaigns
  const { data, isLoading, error } = useQuery({
    queryKey: ['campaigns', statusFilter],
    queryFn: () =>
      campaignApi.list(1, 50, statusFilter === 'all' ? undefined : statusFilter),
    refetchInterval: 5000, // Refetch every 5 seconds
  });

  // GSAP: Animate page entry -- off entirely under prefers-reduced-motion.
  useEffect(() => {
    if (!containerRef.current || !headingRef.current || prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline();

      // Animate heading
      tl.from(headingRef.current, {
        y: -30,
        opacity: 0,
        duration: 0.6,
        ease: 'power3.out',
      });

      // Stagger animate filter buttons
      tl.from(
        '.filter-button',
        {
          x: -20,
          opacity: 0,
          stagger: 0.08,
          duration: 0.4,
        },
        '-=0.3'
      );

      // Animate search bar
      tl.from(
        '.search-bar',
        {
          x: 20,
          opacity: 0,
          duration: 0.4,
        },
        '-=0.3'
      );
    }, containerRef);

    return () => ctx.revert();
  }, []);

  // Filter campaigns by search query
  const filteredCampaigns = data?.items.filter((campaign) =>
    campaign.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Count campaigns by status
  const statusCounts = data?.items.reduce((acc, campaign) => {
    acc[campaign.status] = (acc[campaign.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div ref={containerRef} className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h1
              ref={headingRef}
              className="text-2xl font-semibold text-slate-100 mb-2"
            >
              LinkedIn Campaigns
            </h1>
            <p className="text-muted">
              Manage your automation campaigns
              {isConnected && (
                <span className="ml-2 inline-flex items-center gap-1 text-sm text-success-fg">
                  <motion.span
                    className="w-2 h-2 bg-success-fg rounded-full"
                    animate={
                      prefersReducedMotion()
                        ? undefined
                        : { opacity: [1, 0.3, 1], transition: { duration: 2, repeat: Infinity } }
                    }
                  />
                  Live
                </span>
              )}
            </p>
          </div>

          <motion.button
            whileHover={prefersReducedMotion() ? undefined : { scale: 1.05 }}
            whileTap={prefersReducedMotion() ? undefined : { scale: 0.95 }}
            onClick={() => navigate('/campaigns/new')}
            className="btn-primary min-h-[44px] sm:min-h-0 px-6 py-3"
          >
            <Plus size={20} />
            New Campaign
          </motion.button>
        </div>

        {/* Filters and Search */}
        <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
          {/* Status Filters */}
          <div className="flex flex-wrap gap-2">
            {statusFilters.map((filter) => {
              const count =
                filter.value === 'all'
                  ? data?.total || 0
                  : statusCounts?.[filter.value] || 0;

              return (
                <FilterButton
                  key={filter.value}
                  label={filter.label}
                  count={count}
                  active={statusFilter === filter.value}
                  onClick={() => setStatusFilter(filter.value)}
                />
              );
            })}
          </div>

          {/* Search Bar */}
          <div className="search-bar relative w-full md:w-64">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted"
              size={18}
            />
            <input
              type="text"
              placeholder="Search campaigns..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input w-full pl-10"
            />
          </div>
        </div>
      </div>

      {/* Campaign Grid */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message="Failed to load campaigns" />
      ) : filteredCampaigns && filteredCampaigns.length > 0 ? (
        <motion.div
          layout
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          <AnimatePresence mode="popLayout">
            {filteredCampaigns.map((campaign) => (
              <CampaignCard key={campaign.id} campaign={campaign} />
            ))}
          </AnimatePresence>
        </motion.div>
      ) : (
        <EmptyState
          message={
            searchQuery
              ? 'No campaigns match your search'
              : 'No campaigns yet'
          }
          action={
            !searchQuery && (
              <motion.button
                whileHover={prefersReducedMotion() ? undefined : { scale: 1.05 }}
                whileTap={prefersReducedMotion() ? undefined : { scale: 0.95 }}
                onClick={() => navigate('/campaigns/new')}
                className="btn-primary min-h-[44px] sm:min-h-0 mt-4 px-6 py-3"
              >
                Create Your First Campaign
              </motion.button>
            )
          }
        />
      )}
    </div>
  );
}

interface FilterButtonProps {
  label: string;
  count: number;
  active?: boolean;
  onClick: () => void;
}

function FilterButton({ label, count, active = false, onClick }: FilterButtonProps) {
  const reduced = prefersReducedMotion();
  return (
    <motion.button
      className={clsx(
        'filter-button min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg font-medium text-sm transition-colors',
        active
          ? 'bg-accent/15 text-purple-300 border border-accent/40'
          : 'bg-surface text-muted hover:text-foreground hover:bg-slate-700/60 border border-border'
      )}
      whileHover={reduced ? undefined : { scale: active ? 1 : 1.05 }}
      whileTap={reduced ? undefined : { scale: 0.95 }}
      onClick={onClick}
    >
      {label}
      <span className={clsx('ml-2 text-xs', active ? 'opacity-90' : 'opacity-60')}>
        ({count})
      </span>
    </motion.button>
  );
}

function LoadingState() {
  const reduced = prefersReducedMotion();
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <motion.div
        animate={reduced ? undefined : { rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      >
        <Loader2 size={48} className="text-accent" />
      </motion.div>
      <p className="mt-4 text-muted">Loading campaigns...</p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  const reduced = prefersReducedMotion();
  return (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-20"
    >
      <div className="bg-danger/10 border border-danger/40 rounded-lg p-8 max-w-md text-center">
        <p className="text-danger-fg font-medium">{message}</p>
      </div>
    </motion.div>
  );
}

function EmptyState({
  message,
  action,
}: {
  message: string;
  action?: React.ReactNode;
}) {
  const reduced = prefersReducedMotion();
  return (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-20"
    >
      <div className="text-center">
        <div className="text-6xl mb-4">📊</div>
        <p className="text-lg text-muted mb-2">{message}</p>
        {action}
      </div>
    </motion.div>
  );
}
