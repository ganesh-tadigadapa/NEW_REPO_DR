"use client";
/**
 * Session context for the whole app.
 *
 * Holds what the SERVER says about the current account. It is refreshed on mount and on
 * every navigation, so a doctor approved while they were signed in sees the Reports tab
 * appear without having to work out that they should log in again.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ANONYMOUS, fetchSession, logout as doLogout, type Session } from "@/lib/auth";

type Ctx = Session & {
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<Ctx>({
  ...ANONYMOUS, loading: true,
  refresh: async () => {}, signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthCtx);
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session>(ANONYMOUS);
  const [loading, setLoading] = useState(true);
  const path = usePathname();

  const refresh = useCallback(async () => {
    try {
      // A 401 comes back as ANONYMOUS, which IS a real sign-out and must be applied.
      setSession(await fetchSession());
    } catch {
      // Only a TRANSPORT failure reaches here — the API restarted, or was briefly
      // unreachable. That is not a sign-out, and treating it as one is what made the
      // app "randomly lose the login": this refresh runs on every navigation, so one
      // failed probe dropped the session to ANONYMOUS and Guard bounced the user to
      // /login with a perfectly good token still in localStorage. Keep what we had and
      // let the next navigation re-check.
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-read on every navigation: verification state can change server-side at any time.
  useEffect(() => { refresh(); }, [refresh, path]);

  const signOut = useCallback(async () => {
    await doLogout();
    setSession(ANONYMOUS);
    window.location.href = "/login";
  }, []);

  return (
    <AuthCtx.Provider value={{ ...session, loading, refresh, signOut }}>
      {children}
    </AuthCtx.Provider>
  );
}
