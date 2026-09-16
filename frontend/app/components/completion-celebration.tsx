"use client";

import { CSSProperties, useEffect } from "react";

const CONFETTI_COLORS = ["#f47c20", "#ffc46b", "#fff1cf", "#d96218", "#f3a85b", "#8f4d2e"];

interface CelebrationProps {
  onComplete: () => void;
}

interface ConfettiStyle extends CSSProperties {
  "--confetti-x": string;
  "--confetti-delay": string;
  "--confetti-duration": string;
  "--confetti-drift": string;
  "--confetti-spin": string;
  "--confetti-color": string;
  "--confetti-size": string;
}

export function CompletionCelebration({ onComplete }: CelebrationProps) {
  useEffect(() => {
    const timer = window.setTimeout(onComplete, 3600);
    return () => window.clearTimeout(timer);
  }, [onComplete]);

  const pieces = Array.from({ length: 48 }, (_, index) => {
    const style: ConfettiStyle = {
      "--confetti-x": `${(index * 37 + 7) % 100}%`,
      "--confetti-delay": `${(index % 12) * 45}ms`,
      "--confetti-duration": `${2200 + (index % 7) * 130}ms`,
      "--confetti-drift": `${((index * 29) % 120) - 60}px`,
      "--confetti-spin": `${420 + (index % 6) * 110}deg`,
      "--confetti-color": CONFETTI_COLORS[index % CONFETTI_COLORS.length],
      "--confetti-size": `${6 + (index % 4) * 2}px`,
    };

    return <i key={index} className="confetti-piece" style={style} />;
  });

  return (
    <div className="completion-celebration">
      <div className="confetti-field" aria-hidden="true">{pieces}</div>
      <div className="completion-toast" role="status" aria-live="polite">
        <span>All habits complete</span>
        <strong>Beautiful work today.</strong>
      </div>
    </div>
  );
}
