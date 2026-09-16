"use client";

import { House, ListChecks, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CSSProperties } from "react";

function Destination({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof House; active: boolean }) {
  return (
    <Link className={`nav-item ${active ? "active" : ""}`} href={href} aria-current={active ? "page" : undefined}>
      <Icon size={25} strokeWidth={active ? 2.35 : 1.85} aria-hidden="true" />
      <span>{label}</span>
    </Link>
  );
}

export function BottomNavigation({ onCreate }: { onCreate: () => void }) {
  const pathname = usePathname();
  const habitsActive = pathname.startsWith("/habits");
  const homeActive = !habitsActive;
  const activeIndex = habitsActive ? 2 : 0;

  return (
    <nav className="bottom-nav" aria-label="Primary navigation">
      <div className="bottom-nav-grid" style={{ "--active-index": activeIndex } as CSSProperties}>
        <span className="nav-active-pill" aria-hidden="true" />
        <Destination href="/" label="Home" icon={House} active={homeActive} />
        <button className="nav-item nav-create" onClick={onCreate} aria-label="Create a new habit">
          <span className="nav-create-icon" aria-hidden="true">
            <Plus size={19} strokeWidth={2} />
          </span>
          <span>Add</span>
        </button>
        <Destination href="/habits" label="Habits" icon={ListChecks} active={habitsActive} />
      </div>
    </nav>
  );
}
