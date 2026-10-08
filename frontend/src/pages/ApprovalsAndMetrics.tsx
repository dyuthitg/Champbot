// The review queue and its metrics share the Approvals nav slot: the metrics
// are about the queue, so they sit one sub-tab over rather than in the nav.

import { useNavigate, useLocation } from 'react-router-dom';
import { BarChart3, Inbox } from 'lucide-react';
import { SubTabs, type SubTab } from '@/components/SubTabs';
import { Approvals } from './Approvals';
import { ReviewMetrics } from './ReviewMetrics';

const TABS: readonly (SubTab & { path: string })[] = [
  { key: 'queue', label: 'Queue', icon: Inbox, path: '/approvals' },
  { key: 'metrics', label: 'Metrics', icon: BarChart3, path: '/approvals/metrics' },
];

export function ApprovalsAndMetrics() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = location.pathname.startsWith('/approvals/metrics') ? 'metrics' : 'queue';

  return (
    <div>
      <div className="max-w-5xl mx-auto px-4 pt-4">
        <SubTabs
          tabs={TABS}
          active={active}
          onChange={(key) => navigate(TABS.find((t) => t.key === key)!.path)}
        />
      </div>
      {active === 'metrics' ? <ReviewMetrics /> : <Approvals />}
    </div>
  );
}
