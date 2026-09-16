"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

interface Props { open: boolean; onClose: () => void; onCreate: (name: string) => Promise<void>; }

export function CreateHabitSheet({ open, onClose, onCreate }: Props) {
  const [name, setName] = useState(""); const [error, setError] = useState<string | null>(null); const [submitting, setSubmitting] = useState(false); const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!open) return; const previousFocus = document.activeElement as HTMLElement | null; document.body.style.overflow = "hidden"; const timer = window.setTimeout(() => inputRef.current?.focus(), 120);
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !submitting) onClose(); if (event.key === "Tab") { const sheet = inputRef.current?.closest("[role=dialog]"); const focusable = sheet?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)"); if (!focusable?.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } };
    document.addEventListener("keydown", onKeyDown); return () => { window.clearTimeout(timer); document.body.style.overflow = ""; document.removeEventListener("keydown", onKeyDown); previousFocus?.focus(); };
  }, [open, onClose, submitting]);
  if (!open) return null;
  async function submit(event: FormEvent) { event.preventDefault(); const normalized = name.trim(); if (!normalized) return setError("Give your habit a short, memorable name."); if (normalized.length > 120) return setError("Keep the name to 120 characters or fewer."); setSubmitting(true); setError(null); try { await onCreate(normalized); setName(""); onClose(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create the habit."); } finally { setSubmitting(false); } }
  return <div className="sheet-layer" onMouseDown={(event) => event.target === event.currentTarget && !submitting && onClose()}><section className="create-sheet" role="dialog" aria-modal="true" aria-labelledby="create-title"><div className="sheet-grabber" /><button className="sheet-close" onClick={onClose} disabled={submitting} aria-label="Close create habit"><X size={20} /></button><div className="sheet-heading"><img src="/images/habit-seed.png" alt="" /><h2 id="create-title">New habit</h2></div><form onSubmit={submit}><label className="sr-only" htmlFor="habit-name">Habit name</label><input ref={inputRef} id="habit-name" value={name} onChange={(event) => { setName(event.target.value); setError(null); }} maxLength={120} placeholder="What do you want to repeat?" disabled={submitting} aria-invalid={Boolean(error)} aria-describedby={error ? "habit-name-error" : undefined} /><div className="field-feedback">{error && <span id="habit-name-error" className="field-error">{error}</span>}{name.length >= 100 && <span className="field-count">{name.length}/120</span>}</div><button className="primary-button full-width" disabled={submitting}>{submitting ? "Creating…" : "Create"}</button></form></section></div>;
}
