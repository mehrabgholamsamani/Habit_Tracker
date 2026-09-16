"use client";

import { ArrowRight, ChevronsRight } from "lucide-react";
import { useEffect, useState } from "react";

const LAST_STEP = 2;

export function OnboardingFlow({ onCreate, onSkip }: { onCreate: () => void; onSkip: () => Promise<void> }) {
  const [step, setStep] = useState(0);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem("focus-tiger-onboarding-step"));
    if (Number.isInteger(saved) && saved >= 0 && saved <= LAST_STEP) setStep(saved);
  }, []);

  function go(next: number) {
    setStep(next);
    window.localStorage.setItem("focus-tiger-onboarding-step", String(next));
  }

  async function skip() {
    setLeaving(true);
    try { await onSkip(); } finally { setLeaving(false); }
  }

  return (
    <main className="onboarding" aria-label="Welcome to Focus Tiger">
      <div className="onboarding-topbar">
        <span />
        {step > 0 && <button className="onboarding-skip" onClick={skip} disabled={leaving} aria-label="Skip onboarding"><ChevronsRight size={22} strokeWidth={2} /></button>}
      </div>

      <section className="onboarding-stage" key={step}>
        {step === 0 && <>
          <div className="tora-scene"><img src="/images/tora-onboarding.png" alt="Tora, the Focus Tiger mascot, waving hello" /></div>
          <div className="onboarding-copy welcome-copy"><h1>Meet Tora.</h1><p className="onboarding-description">Small steps. Real momentum.</p></div>
        </>}

        {step === 1 && <>
          <div className="condition-demo"><img src="/images/daily-condition.png" alt="Daily condition showing a balanced level between too low and too high" /></div>
          <div className="onboarding-copy lesson-copy"><h1>Find your pace.</h1><p className="onboarding-description">Enough to grow. Never too much.</p></div>
        </>}

        {step === 2 && <>
          <div className="rhythm-demo"><img src="/images/focus-rhythm-path.png" alt="A seven-day activity path with today highlighted" /></div>
          <div className="onboarding-copy lesson-copy"><h1>Build your rhythm.</h1><p className="onboarding-description">Every day is a fresh start.</p></div>
        </>}
      </section>

      <footer className="onboarding-footer">
        <div className="onboarding-progress" aria-label={`Step ${step + 1} of 3`}>{[0,1,2].map((item) => <button key={item} className={item === step ? "active" : ""} onClick={() => go(item)} aria-label={`Go to step ${item + 1}`} aria-current={item === step ? "step" : undefined} />)}</div>
        <button className="onboarding-primary" onClick={() => step < LAST_STEP ? go(step + 1) : onCreate()} aria-label={step < LAST_STEP ? "Continue" : "Create my first habit"}>{step < LAST_STEP ? <ArrowRight size={24} strokeWidth={2.2} /> : "Create my first habit"}</button>
      </footer>
    </main>
  );
}
