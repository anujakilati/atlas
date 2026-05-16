import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { fetchUserProfile, validateSession } from "@/lib/auth";
import { clearLocalAuthSession, supabase } from "@/lib/supabase";

type AuthContextValue = {
  session: Session | null;
  profile: Awaited<ReturnType<typeof fetchUserProfile>>;
  loading: boolean;
  refreshProfile: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof fetchUserProfile>>>(null);
  const [loading, setLoading] = useState(true);
  const profileUserId = useRef<string | null>(null);

  const loadProfile = useCallback(async (userId: string, force = false) => {
    if (!force && profileUserId.current === userId) return;
    profileUserId.current = userId;
    try {
      const nextProfile = await fetchUserProfile(userId);
      setProfile(nextProfile);
    } catch {
      setProfile(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    const userId = session?.user?.id;
    if (!userId) return;
    profileUserId.current = null;
    await loadProfile(userId, true);
  }, [session?.user?.id, loadProfile]);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      const user = await validateSession();
      if (!mounted) return;

      if (!user) {
        setSession(null);
        setProfile(null);
        setLoading(false);
        return;
      }

      const { data } = await supabase.auth.getSession();
      setSession(data.session);
      await loadProfile(user.id);
      if (mounted) setLoading(false);
    };

    void bootstrap();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, nextSession) => {
      if (!mounted) return;

      setSession(nextSession);

      if (event === "TOKEN_REFRESHED") {
        setLoading(false);
        return;
      }

      const userId = nextSession?.user?.id;
      if (!userId) {
        profileUserId.current = null;
        setProfile(null);
        setLoading(false);
        return;
      }

      if (event === "SIGNED_OUT") {
        await clearLocalAuthSession();
        profileUserId.current = null;
        setProfile(null);
        setLoading(false);
        return;
      }

      await loadProfile(userId);
      if (mounted) setLoading(false);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, [loadProfile]);

  const value = useMemo(
    () => ({ session, profile, loading, refreshProfile }),
    [session, profile, loading, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
