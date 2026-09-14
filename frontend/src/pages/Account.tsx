import { useClerk, useUser } from '@clerk/clerk-react';
import { LogOut, ShieldCheck, UserCircle2 } from 'lucide-react';
import { Button, Card, EmptyState } from '@/components/ui';
import { authEnabled } from '@/lib/clerk';

/**
 * Who this browser is signed in as, and a way out. Separate from
 * /accounts (the connected LinkedIn accounts) on purpose -- this page is
 * about the person operating the tool, not the accounts it acts on behalf of.
 */
export function Account() {
  if (!authEnabled) {
    return (
      <EmptyState
        icon={<UserCircle2 size={40} />}
        title="No sign-in configured on this deploy"
        body="VITE_CLERK_PUBLISHABLE_KEY isn't set, so there's nothing to sign in or out of -- every screen here is open."
      />
    );
  }
  return <SignedInAccount />;
}

function SignedInAccount() {
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();

  if (!isLoaded) {
    return null;
  }

  const email = user?.primaryEmailAddress?.emailAddress ?? 'unknown';

  return (
    <div className="max-w-xl mx-auto px-4 py-10">
      <h1 className="text-xl font-semibold text-foreground mb-1">Account</h1>
      <p className="text-muted text-sm mb-6">
        Who this browser is signed in as, and a way out.
      </p>

      <Card className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          {user?.imageUrl ? (
            <img src={user.imageUrl} alt="" className="w-10 h-10 rounded-full shrink-0" />
          ) : (
            <UserCircle2 size={40} className="text-muted shrink-0" />
          )}
          <div className="min-w-0">
            <div className="text-foreground font-medium truncate">{email}</div>
            <div className="text-xs text-success-fg flex items-center gap-1 mt-0.5">
              <ShieldCheck size={13} />
              Signed in
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          icon={<LogOut size={16} />}
          onClick={() => signOut()}
          className="shrink-0 whitespace-nowrap"
        >
          Sign out
        </Button>
      </Card>
    </div>
  );
}
