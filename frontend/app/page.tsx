"use client";

import { Check, ChevronDown, ChevronUp, CircleCheck, Flame, LoaderCircle, Sparkles, Trophy } from "lucide-react";
import { useApp } from "./components/app-provider";

export default function TodayPage() {
  const { user, habits, loading, error, checkingInId, checkIn, undoCheckIn, openCreate } = useApp();
  const completed = habits.filter((habit) => habit.completed_today).length;
  const total = habits.length;
  const progress = total ? Math.round((completed / total) * 100) : 0;
  const currentStreak = habits.reduce((best, habit) => Math.max(best, habit.current_streak), 0);
  const personalBest = habits.reduce((best, habit) => Math.max(best, habit.longest_streak), 0);
  const nextHabit = habits.find((habit) => !habit.completed_today);
  const allDone = total > 0 && completed === total;

  return (
    <section className="today-dashboard">
      <div className="sanctuary-hero">
        <img className="sanctuary-image" src="/images/tora-sanctuary-home.png" alt="Tora guiding a glowing focus crystal in a bright sanctuary" />
        <header className="sanctuary-topbar">
          <strong>Hi, {user?.name.split(" ")[0] ?? "Tiger"}</strong>
          <div className="sanctuary-actions"><span className="streak-chip"><Flame size={17} fill="currentColor" />{currentStreak}</span></div>
        </header>
        <div className="sanctuary-score-zone">
          <div className="momentum-score"><span>Today</span><strong>{loading ? "—" : progress}</strong><small>%</small>{progress > 0 && <ChevronUp size={22} aria-label="Progressing" />}</div>
          <div className="score-connector" aria-hidden="true" />
          <div className="momentum-metrics" aria-label="Habit summary">
            <article><div><CircleCheck size={17} /><strong>{completed}/{total}</strong></div><span>Complete</span></article>
            <article><div><Flame size={17} /><strong>{currentStreak}</strong></div><span>Streak</span></article>
            <article><div><Trophy size={17} /><strong>{personalBest}</strong></div><span>Best</span></article>
          </div>
        </div>
      </div>

      <div className="momentum-panel">
        {error && <div className="notice notice-error">{error}</div>}
        {!loading && (nextHabit ? (
          <article className="next-habit-card">
            <div className="next-habit-title"><div><p>Up next</p><h2>{nextHabit.name}</h2></div></div>
            <button type="button" className="next-check-button" disabled={checkingInId === nextHabit.id} onClick={() => checkIn(nextHabit.id)} aria-label={`Check in ${nextHabit.name}`}>{checkingInId === nextHabit.id ? <LoaderCircle size={22} className="spin" /> : <Check size={24} strokeWidth={2.8} />}</button>
          </article>
        ) : allDone ? (
          <article className="next-habit-card all-done"><div className="next-habit-title"><div><p>Today is complete</p><h2>Beautiful work.</h2></div><div className="next-complete-crystal" aria-hidden="true"><Check size={24} strokeWidth={2.8} /></div></div></article>
        ) : (
          <article className="next-habit-card empty-next"><div className="next-habit-title"><div><p>Your first step</p><h2>Choose one small habit.</h2></div><div className="next-orb"><Sparkles size={24} /></div></div><button className="next-create-button" onClick={openCreate}>Create</button></article>
        ))}

        {total > 0 && <details className="all-habits-drawer" open><summary><span>Today&apos;s habits</span><span>{completed}/{total}<ChevronDown size={17} /></span></summary><div className="compact-habit-list">{habits.map((habit) => { const updating = checkingInId === habit.id; return <button type="button" key={habit.id} className={habit.completed_today ? "done" : ""} disabled={updating} onClick={() => habit.completed_today ? undoCheckIn(habit.id) : checkIn(habit.id)} aria-pressed={habit.completed_today} aria-label={habit.completed_today ? `Undo check-in for ${habit.name}` : `Check in ${habit.name}`}><strong>{habit.name}</strong><span>{updating ? <><LoaderCircle size={15} className="spin" /> Updating</> : habit.completed_today ? "Done · tap to undo" : "Tap to check in"}</span></button>; })}</div></details>}
      </div>
    </section>
  );
}
