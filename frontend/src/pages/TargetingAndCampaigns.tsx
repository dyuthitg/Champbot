// Targeting (who to contact) and Campaigns (the sends themselves) share one
// nav slot -- they're two views on the same outreach work, not two separate
// products, so a sub-tab strip switches between them instead of a full tab.

import { useNavigate, useLocation } from 'react-router-dom';
import { Megaphone, Target as TargetIcon } from 'lucide-react';
import { SubTabs, type SubTab } from '@/components/SubTabs';
import { CampaignList } from './CampaignList';
import { Targeting } from './Targeting';

const TABS: readonly (SubTab & { path: string })[] = [
  { key: 'targeting', label: 'Targeting', icon: TargetIcon, path: '/targeting' },
  { key: 'campaigns', label: 'Campaigns', icon: Megaphone, path: '/campaigns' },
];

export function TargetingAndCampaigns() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = location.pathname.startsWith('/campaigns') ? 'campaigns' : 'targeting';

  return (
    <div>
      <div className="max-w-7xl mx-auto px-4 pt-4">
        <SubTabs
          tabs={TABS}
          active={active}
          onChange={(key) => navigate(TABS.find((t) => t.key === key)!.path)}
        />
      </div>
      {active === 'campaigns' ? <CampaignList /> : <Targeting />}
    </div>
  );
}
