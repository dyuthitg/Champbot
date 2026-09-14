import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnimatePresence, motion, MotionConfig } from 'framer-motion';
import { Account } from './pages/Account';
import { Accounts } from './pages/Accounts';
import { AgentMonitor } from './pages/AgentMonitor';
import { Approvals } from './pages/Approvals';
import { CampaignDetail } from './pages/CampaignDetail';
import { CampaignList } from './pages/CampaignList';
import { CreateCampaign } from './pages/CreateCampaign';
import { Dashboard } from './pages/Dashboard';
import { Targeting } from './pages/Targeting';
import { Warmup } from './pages/Warmup';
import { Navigation } from './components/Navigation';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 3000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* reducedMotion="user" is the one-line version of what index.css and
          the GSAP call sites do by hand for everything else: when the OS
          says reduce motion, every whileHover/whileTap/initial/animate in
          the app snaps straight to its end state instead of animating.
          Nothing here needs to move to be understood, so "off" is the
          correct behaviour, not "shorter." */}
      <MotionConfig reducedMotion="user">
        <BrowserRouter>
          <div className="min-h-screen bg-background">
            <Navigation />
            <AnimatedRoutes />
          </div>
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  );
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Page><Dashboard /></Page>} />
        <Route path="/approvals" element={<Page><Approvals /></Page>} />
        <Route path="/accounts" element={<Page><Accounts /></Page>} />
        <Route path="/warmup" element={<Page><Warmup /></Page>} />
        <Route path="/targeting" element={<Page><Targeting /></Page>} />
        <Route path="/campaigns" element={<Page><CampaignList /></Page>} />
        <Route path="/campaigns/new" element={<Page><CreateCampaign /></Page>} />
        <Route path="/campaigns/:id" element={<Page><CampaignDetail /></Page>} />
        <Route path="/agents" element={<Page><AgentMonitor /></Page>} />
        <Route path="/account" element={<Page><Account /></Page>} />
        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      {children}
    </motion.div>
  );
}

export default App;
