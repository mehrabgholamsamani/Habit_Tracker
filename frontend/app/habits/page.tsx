"use client";

import { Check, Ellipsis, LoaderCircle, Pencil, Trash2, X } from "lucide-react";
import { FormEvent, useState } from "react";
import { useApp } from "../components/app-provider";

export default function HabitsPage() {
  const { habits, loading, error: appError, checkingInId, checkIn, undoCheckIn, deleteHabit, renameHabit, openCreate } = useApp();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [menuId, setMenuId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  function beginEdit(id: number, currentName: string) {
    setEditingId(id);
    setMenuId(null);
    setName(currentName);
    setError(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editingId || !name.trim()) return;
    const habitId = editingId;
    setBusyId(editingId);
    setError(null);
    try {
      await renameHabit(habitId, name.trim());
      setEditingId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not rename habit.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Remove this habit and its check-in history?")) return;
    setBusyId(id);
    setMenuId(null);
    setError(null);
    try {
      await deleteHabit(id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove habit.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="habits-screen">
      <header className="habits-hero">
        <img src="/images/tora-habit-garden.png" alt="Tora tending four glowing habits in the sanctuary garden" />
        <h1>Habits</h1>
        <div className="habits-count" aria-label={`${habits.length} active habits`}>
          <strong>{habits.length}</strong>
          <span>active</span>
        </div>
      </header>

      <div className="habits-panel">
        {(error || appError) && <div className="habits-error" role="alert">{error || appError}</div>}

        {loading ? (
          <div className="habits-loading" aria-label="Loading habits"><span /><span /><span /></div>
        ) : habits.length === 0 ? (
          <div className="habits-empty">
            <h2>No habits yet</h2>
            <button onClick={openCreate}>Add habit</button>
          </div>
        ) : (
          <div className="habit-ledger">
            {habits.map((habit) => (
              <article className={`habit-row ${habit.completed_today ? "is-complete" : ""}`} key={habit.id}>
                {editingId === habit.id ? (
                  <form className="habit-row-edit" onSubmit={save}>
                    <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} autoFocus disabled={busyId === habit.id} aria-label="Habit name" />
                    <button type="submit" disabled={busyId === habit.id} aria-label="Save habit name"><Check size={18} /></button>
                    <button type="button" onClick={() => setEditingId(null)} disabled={busyId === habit.id} aria-label="Cancel editing"><X size={18} /></button>
                  </form>
                ) : (
                  <>
                    <button type="button" className={`habit-row-copy ${habit.completed_today ? "done" : ""}`} onClick={() => habit.completed_today ? undoCheckIn(habit.id) : checkIn(habit.id)} disabled={checkingInId === habit.id || busyId === habit.id} aria-pressed={habit.completed_today} aria-label={habit.completed_today ? `Undo check-in for ${habit.name}` : `Check in ${habit.name}`}>
                      <h2>{habit.name}</h2>
                      <p>{checkingInId === habit.id ? <><LoaderCircle size={13} className="spin" /> Updating…</> : habit.completed_today ? "✓ Completed today · tap to undo" : habit.current_streak ? `${habit.current_streak} day streak · tap to check in` : "Tap to check in"}</p>
                    </button>
                    <div className={`habit-row-actions ${menuId === habit.id ? "open" : ""}`}>
                      {menuId === habit.id && (
                        <>
                          <button type="button" onClick={() => beginEdit(habit.id, habit.name)} disabled={busyId === habit.id || checkingInId === habit.id} aria-label={`Edit ${habit.name}`} title="Edit habit"><Pencil size={17} /></button>
                          <button type="button" className="danger" onClick={() => remove(habit.id)} disabled={busyId === habit.id || checkingInId === habit.id} aria-label={`Remove ${habit.name}`} title="Delete habit">{busyId === habit.id ? <LoaderCircle size={17} className="spin" /> : <Trash2 size={17} />}</button>
                        </>
                      )}
                      <button type="button" className="habit-more" onClick={() => setMenuId(menuId === habit.id ? null : habit.id)} disabled={busyId === habit.id || checkingInId === habit.id} aria-label={`Actions for ${habit.name}`} aria-expanded={menuId === habit.id}><Ellipsis size={20} /></button>
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
