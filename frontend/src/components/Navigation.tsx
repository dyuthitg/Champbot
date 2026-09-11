import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Activity, Flame, Inbox, LayoutDashboard, Target, User, Users } from 'lucide-react';
import { clsx } from 'clsx';
import { outreachApi } from '@/lib/api';

const navItems = [
  { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { path: '/approvals', label: 'Approvals', icon: Inbox, badge: true },
  { path: '/warmup', label: 'Warm-up', icon: Flame },
  { path: '/targeting', label: 'Targeting', icon: Target },
  { path: '/accounts', label: 'Accounts', icon: Users },
  { path: '/agents', label: 'Agents', icon: Activity },
  { path: '/account', label: 'Account', icon: User },
];

export function Navigation() {
  const location = useLocation();

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
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-16 gap-4">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <motion.div
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="text-lg font-bold bg-gradient-to-r from-purple-400 to-amber-300 bg-clip-text text-transparent"
            >
              Social Bot
            </motion.div>
          </Link>

          <div className="flex items-center gap-1 overflow-x-auto">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.path);
              const showBadge = item.badge && pending > 0;

              return (
                <Link key={item.path} to={item.path}>
                  <motion.div
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    className={clsx(
                      'relative flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap',
                      isActive
                        ? 'bg-purple-500/15 text-purple-300'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200',
                    )}
                  >
                    <Icon size={17} />
                    <span className="hidden sm:inline">{item.label}</span>
                    {showBadge && (
                      <span className="ml-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-purple-500 text-white text-[11px] font-semibold flex items-center justify-center">
                        {pending}
                      </span>
                    )}
                  </motion.div>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
