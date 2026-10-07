// Who's signed in, shown the way most products show it: a small avatar in
// the corner, not a whole tab of its own. Click it and everything that used
// to live on the "Login Account" page -- email, signed-in state, sign out --
// shows up in a dropdown right there.
//
// The badge always renders, even with no auth provider configured -- a
// blank corner where a tab used to be reads as "this broke," not "there's
// nothing to show." In that demo-mode case it opens to an explanation
// instead of account details.

import { useEffect, useRef, useState } from 'react';
import { useClerk, useUser } from '@clerk/clerk-react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, LogOut, ShieldCheck, UserCircle2 } from 'lucide-react';
import { authEnabled } from '@/lib/clerk';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function initials(name: string) {
  return name.trim().slice(0, 2).toUpperCase();
}

export function AccountBadge() {
  return authEnabled ? <SignedInBadge /> : <DemoModeBadge />;
}

// The dropdown shell: the avatar button, the open/close state, and the
// outside-click / Escape handling every variant needs. Each variant just
// supplies what the avatar looks like and what the panel says.
function BadgeShell({
  avatar,
  panel,
}: {
  avatar: React.ReactNode;
  panel: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 p-1 pr-2 rounded-full hover:bg-slate-800 transition-colors"
      >
        {avatar}
        <ChevronDown
          size={14}
          className={`text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={reduced ? undefined : { opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? undefined : { opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 mt-2 w-64 rounded-xl bg-slate-800 border border-slate-700 shadow-xl overflow-hidden z-50"
          >
            {panel}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SignedInBadge() {
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();

  if (!isLoaded) return null;

  const email = user?.primaryEmailAddress?.emailAddress ?? 'unknown';

  return (
    <BadgeShell
      avatar={
        user?.imageUrl ? (
          <img src={user.imageUrl} alt="" className="w-8 h-8 rounded-full ring-1 ring-slate-700" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-semibold ring-1 ring-slate-700">
            {initials(email)}
          </div>
        )
      }
      panel={
        <>
          <div className="flex items-center gap-3 p-3.5 border-b border-slate-700">
            {user?.imageUrl ? (
              <img src={user.imageUrl} alt="" className="w-9 h-9 rounded-full shrink-0" />
            ) : (
              <UserCircle2 size={36} className="text-slate-500 shrink-0" />
            )}
            <div className="min-w-0">
              <div className="text-sm text-slate-100 font-medium truncate">{email}</div>
              <div className="text-xs text-success-fg flex items-center gap-1 mt-0.5">
                <ShieldCheck size={12} />
                Signed in
              </div>
            </div>
          </div>

          <button
            onClick={() => signOut()}
            className="w-full flex items-center gap-2 px-3.5 py-2.5 text-sm text-slate-300 hover:bg-slate-700/60 hover:text-slate-100 transition-colors"
          >
            <LogOut size={15} />
            Sign out
          </button>
        </>
      }
    />
  );
}

// No VITE_CLERK_PUBLISHABLE_KEY on this deploy -- there's no one to sign in
// or out of, but the badge still shows up and says so, rather than
// disappearing without explanation.
function DemoModeBadge() {
  return (
    <BadgeShell
      avatar={
        <div className="w-8 h-8 rounded-full bg-slate-700/60 text-slate-400 flex items-center justify-center ring-1 ring-slate-700">
          <UserCircle2 size={19} />
        </div>
      }
      panel={
        <div className="p-3.5">
          <div className="text-sm text-slate-100 font-medium">No sign-in configured</div>
          <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
            This deploy doesn't have sign-in set up, so every screen here is open -- there's
            nothing to sign in or out of.
          </p>
        </div>
      }
    />
  );
}
