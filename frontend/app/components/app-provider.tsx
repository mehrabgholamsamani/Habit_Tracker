"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { BottomNavigation } from "./bottom-navigation";
import { CompletionCelebration } from "./completion-celebration";
import { CreateHabitSheet } from "./create-habit-sheet";
import { OnboardingFlow } from "./onboarding-flow";

// Keep browser traffic same-origin. Next.js proxies /api to the backend service,
// so this also works when the site is opened from a hostname other than localhost.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";
export interface Checkin { id: number; habit_id: number; checked_at: string; checked_on: string; }
export interface Habit { id: number; user_id: number; name: string; created_at: string; current_streak: number; longest_streak: number; completed_today: boolean; checkins: Checkin[]; }
export interface User { id: number; name: string; email: string; onboarding_completed_at: string | null; onboarding_version: number; }
interface AppContextValue { user: User | null; habits: Habit[]; loading: boolean; error: string | null; checkingInId: number | null; checkIn: (id: number) => Promise<void>; undoCheckIn: (id: number) => Promise<void>; createHabit: (name: string) => Promise<void>; deleteHabit: (id: number) => Promise<void>; renameHabit: (id: number, name: string) => Promise<void>; openCreate: () => void; }
const AppContext = createContext<AppContextValue | null>(null);

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail ?? "Something went wrong. Please try again."); }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null); const [habits, setHabits] = useState<Habit[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null); const [checkingInId, setCheckingInId] = useState<number | null>(null); const [createOpen, setCreateOpen] = useState(false);
  const [celebrationId, setCelebrationId] = useState(0);
  const completionStateReady = useRef(false);
  const previousAllDone = useRef(false);
  const completionTriggeredByCheckIn = useRef(false);
  const headers = useCallback((json = false): HeadersInit => ({ ...(json ? { "Content-Type": "application/json" } : {}), ...(user ? { "X-User-Id": String(user.id) } : {}) }), [user]);
  useEffect(() => { apiRequest<User[]>("/users").then((users) => { if (!users.length) throw new Error("No demo user is available."); setUser(users[0]); }).catch((reason: Error) => { setError(reason.message); setLoading(false); }); }, []);
  useEffect(() => { if (!user) return; setLoading(true); apiRequest<Habit[]>("/habits", { headers: { "X-User-Id": String(user.id) } }).then(setHabits).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)); }, [user]);
  useEffect(() => {
    if (loading) return;
    const allDone = habits.length > 0 && habits.every((habit) => habit.completed_today);
    if (!completionStateReady.current) {
      completionStateReady.current = true;
      previousAllDone.current = allDone;
      completionTriggeredByCheckIn.current = false;
      return;
    }
    if (completionTriggeredByCheckIn.current && allDone && !previousAllDone.current) {
      setCelebrationId((current) => current + 1);
    }
    completionTriggeredByCheckIn.current = false;
    previousAllDone.current = allDone;
  }, [habits, loading]);

  async function checkIn(habitId: number) { if (!user) return; setCheckingInId(habitId); setError(null); try { const habit = await apiRequest<Habit>(`/habits/${habitId}/checkins`, { method: "POST", headers: headers() }); completionTriggeredByCheckIn.current = true; setHabits((current) => current.map((item) => item.id === habit.id ? habit : item)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Check-in failed."); } finally { setCheckingInId(null); } }
  async function undoCheckIn(habitId: number) { if (!user) return; setCheckingInId(habitId); setError(null); try { const habit = await apiRequest<Habit>(`/habits/${habitId}/checkins/today`, { method: "DELETE", headers: headers() }); setHabits((current) => current.map((item) => item.id === habit.id ? habit : item)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not undo check-in."); } finally { setCheckingInId(null); } }
  async function createHabit(name: string) { setError(null); const habit = await apiRequest<Habit>("/habits", { method: "POST", headers: headers(true), body: JSON.stringify({ name }) }); setHabits((current) => [...current, habit]); }
  async function completeOnboarding() { if (!user) return; const updated = await apiRequest<User>("/users/me/onboarding", { method: "PATCH", headers: headers(true), body: JSON.stringify({ version: 1 }) }); setUser(updated); window.localStorage.removeItem("focus-tiger-onboarding-step"); }
  async function deleteHabit(habitId: number) { setError(null); await apiRequest<void>(`/habits/${habitId}`, { method: "DELETE", headers: headers() }); setHabits((current) => current.filter((habit) => habit.id !== habitId)); }
  async function renameHabit(habitId: number, name: string) { setError(null); const habit = await apiRequest<Habit>(`/habits/${habitId}`, { method: "PATCH", headers: headers(true), body: JSON.stringify({ name }) }); setHabits((current) => current.map((item) => item.id === habit.id ? habit : item)); }
  const value = useMemo(() => ({ user, habits, loading, error, checkingInId, checkIn, undoCheckIn, createHabit, deleteHabit, renameHabit, openCreate: () => setCreateOpen(true) }), [user, habits, loading, error, checkingInId]);
  const onboardingUser = user?.onboarding_completed_at === null ? user : null;
  const onboarding = Boolean(onboardingUser);
  async function createFromOnboarding(name: string) { await createHabit(name); await completeOnboarding(); }
  return <AppContext.Provider value={value}><div className={`app-canvas ${onboarding ? "is-onboarding" : ""}`}>{!user && loading ? <div className="app-boot" aria-label="Loading Focus Tiger"><img src="/images/tiger-logo.png" alt="" /></div> : onboardingUser ? <OnboardingFlow onCreate={() => setCreateOpen(true)} onSkip={completeOnboarding} /> : <><main className="app-content">{children}</main><BottomNavigation onCreate={() => setCreateOpen(true)} /></>}<CreateHabitSheet open={createOpen} onClose={() => setCreateOpen(false)} onCreate={onboarding ? createFromOnboarding : createHabit} />{celebrationId > 0 && <CompletionCelebration key={celebrationId} onComplete={() => setCelebrationId(0)} />}</div></AppContext.Provider>;
}
export function useApp() { const context = useContext(AppContext); if (!context) throw new Error("useApp must be used inside AppProvider"); return context; }
