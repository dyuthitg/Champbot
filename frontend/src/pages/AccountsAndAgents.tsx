// LinkedIn Accounts, Agents and Warm-up share one nav slot -- all three are
// about the health and behaviour of the accounts the system acts as, so a
// sub-tab strip switches between them instead of three separate tabs.
// Warm-up in particular isn't a destination on its own -- it's a phase an
// account goes through -- so it doesn't get its own top-level tab.

import { useNavigate, useLocation } from 'react-router-dom';
import { Activity, Flame, Users } from 'lucide-react';
import { SubTabs, type SubTab } from '@/components/SubTabs';
import { AgentMonitor } from './AgentMonitor';
import { Accounts } from './Accounts';
import { Warmup } from './Warmup';

const TABS: readonly (SubTab & { path: string })[] = [
  { key: 'accounts', label: 'LinkedIn Accounts', icon: Users, path: '/accounts' },
  { key: 'warmup', label: 'Warm-up', icon: Flame, path: '/warmup' },
  { key: 'agents', label: 'Agents', icon: Activity, path: '/agents' },
];

export function AccountsAndAgents() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = location.pathname.startsWith('/agents')
    ? 'agents'
    : location.pathname.startsWith('/warmup')
      ? 'warmup'
      : 'accounts';

  return (
    <div>
      <div className="max-w-7xl mx-auto px-4 pt-4">
        <SubTabs
          tabs={TABS}
          active={active}
          onChange={(key) => navigate(TABS.find((t) => t.key === key)!.path)}
        />
      </div>
      {active === 'agents' ? <AgentMonitor /> : active === 'warmup' ? <Warmup /> : <Accounts />}
    </div>
  );
}
