// Clerk auth provider (graceful).
//
// When VITE_CLERK_PUBLISHABLE_KEY is set, the app is wrapped in Clerk and gated
// behind sign-in, and the API client is given a token getter. When it is unset
// (e.g. a first deploy before keys are configured), the app renders in demo mode
// with no auth so the deployed link is immediately testable.

import { useEffect } from 'react';
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  RedirectToSignIn,
  useAuth,
} from '@clerk/clerk-react';
import { setAuthTokenGetter } from './api';

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as
  | string
  | undefined;

export const authEnabled = Boolean(PUBLISHABLE_KEY);

// Local-only dev token: {"sub":"local-dev-ui","email":"local@example.com","exp":9999999999},
// HS256-signed with the same throwaway secret scripts/validate_account.py uses. The signature
// is never checked when the backend runs with CLERK_DEV_UNSAFE=true, so this only unlocks
// anything against a server explicitly opted into that insecure mode.
const LOCAL_DEV_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJsb2NhbC1kZXYtdWkiLCJlbWFpbCI6ImxvY2FsQGV4YW1wbGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ.gp7gcH7pYxamP0CUbl7GT45KEmFOD3r1TA2UuuJAH0Q';

function TokenBridge() {
  const { getToken, isSignedIn } = useAuth();
  useEffect(() => {
    setAuthTokenGetter(async () => (isSignedIn ? await getToken() : null));
    return () => setAuthTokenGetter(null);
  }, [getToken, isSignedIn]);
  return null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (!authEnabled) {
    // Demo mode: no Clerk configured. In a local dev server (not a production
    // build) attach the throwaway dev token so the app is actually usable
    // against a backend running with CLERK_DEV_UNSAFE=true; a real deploy
    // still renders with no token at all.
    if (import.meta.env.DEV) {
      setAuthTokenGetter(async () => LOCAL_DEV_TOKEN);
    }
    return <>{children}</>;
  }
  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY!}>
      <TokenBridge />
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </ClerkProvider>
  );
}
