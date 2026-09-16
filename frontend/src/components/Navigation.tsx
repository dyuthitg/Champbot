import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Inbox, LayoutDashboard, Target, Users } from 'lucide-react';
import { clsx } from 'clsx';
import { outreachApi } from '@/lib/api';
import { AccountBadge } from './AccountBadge';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Some tabs fold several routes together (see TargetingAndCampaigns,
// AccountsAndAgents) -- `matches` lists every path that should light this
// tab up, so warm-up and agents don't need a nav item of their own.
const navItems = [
  { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { path: '/approvals', label: 'Approvals', icon: Inbox, badge: true },
  {
    path: '/targeting',
    label: 'Targeting & Campaigns',
    icon: Target,
    matches: ['/targeting', '/campaigns'],
  },
  {
    path: '/accounts',
    label: 'LinkedIn Accounts & Agents',
    icon: Users,
    matches: ['/accounts', '/agents', '/warmup'],
  },
];

export function Navigation() {
  const location = useLocation();
  const reduced = prefersReducedMotion();

  // The pending count lives in the nav because it is the one number that
  // should pull the user back into the product.
  const { data: dashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: outreachApi.dashboard,
    refetchInterval: 30_000,
    retry: false,
  });
  const pending = dashboard?.totals?.pending_review ?? 0;

  return (
    <nav className="bg-slate-900/80 backdrop-blur border-b border-slate-800 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-2 sm:px-4">
        <div className="flex items-center gap-2 sm:gap-4 h-16">
          <Link to="/" className="flex items-center gap-2 shrink-0 pl-2">
            {/* tabIndex={-1}: whileTap makes framer-motion add its own
                tabIndex=0 for keyboard tap support, which turned this into
                a second, silent Tab stop right after the Link itself --
                nothing to press Enter on, just an empty ring. The Link
                already carries the click/keyboard action. */}
            <motion.div
              whileHover={reduced ? undefined : { scale: 1.03 }}
              whileTap={reduced ? undefined : { scale: 0.97 }}
              tabIndex={-1}
              className="text-lg font-bold bg-gradient-to-r from-purple-400 to-amber-300 bg-clip-text text-transparent"
            >
              Social Bot
            </motion.div>
          </Link>

          {/* Every label stays on screen, always -- below tablet width this
              scrolls sideways instead of dropping to icons-only. The edge
              fade is the hint that there's more to scroll to; it used to be
              a bare cut-off with no clue a 6th item existed at all (Week 1
              audit). */}
          <div
            className="flex items-center gap-1 overflow-x-auto flex-1 min-w-0 py-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
            style={{
              maskImage: 'linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent)',
              WebkitMaskImage:
                'linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent)',
            }}
          >
            {navItems.map((item) => {
              const Icon = item.icon;
              // A path boundary (exact match, or the next char is "/")
              // rather than plain startsWith -- otherwise "/targeting-x"
              // would light up the "/targeting" tab too.
              const isActive = (item.matches ?? [item.path]).some(
                (p) => location.pathname === p || location.pathname.startsWith(`${p}/`),
              );
              const showBadge = item.badge && pending > 0;

              return (
                <Link key={item.path} to={item.path} className="shrink-0">
                  <div
                    className={clsx(
                      'relative flex items-center gap-1.5 sm:gap-2 min-h-[44px] px-2.5 sm:px-3 py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors whitespace-nowrap',
                      isActive
                        ? 'bg-purple-500/15 text-purple-300'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200',
                    )}
                  >
                    <Icon size={17} className="shrink-0" />
                    <span>{item.label}</span>
                    {showBadge && (
                      <span className="ml-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-purple-500 text-white text-[11px] font-semibold flex items-center justify-center">
                        {pending}
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>

          <AccountBadge />
        </div>
      </div>
    </nav>
  );
}
