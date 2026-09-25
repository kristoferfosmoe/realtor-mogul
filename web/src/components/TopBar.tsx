"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const NAV = [
  { href: "/", label: "ANALYZER" },
  { href: "/markets", label: "MARKETS" },
  { href: "/portfolio", label: "PORTFOLIO" },
  { href: "/watchlist", label: "WATCHLIST" },
];
const COMING = ["SCREENER"];

export function TopBar() {
  const pathname = usePathname();
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    const ping = () =>
      api
        .health()
        .then(() => setApiUp(true))
        .catch(() => setApiUp(false));
    void ping();
    const healthTimer = setInterval(ping, 15_000);
    const clockTimer = setInterval(() => setNow(new Date()), 1_000);
    return () => {
      clearInterval(healthTimer);
      clearInterval(clockTimer);
    };
  }, []);

  return (
    <header className="topbar">
      <Link href="/" className="brand">
        <span className="brand-mark">RM</span>
        <span className="brand-name">
          REALTOR<span>MOGUL</span>
        </span>
      </Link>
      <nav className="nav">
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={
              pathname === n.href || (n.href !== "/" && pathname.startsWith(`${n.href}/`))
                ? "active"
                : ""
            }
          >
            {n.label}
          </Link>
        ))}
        {COMING.map((label) => (
          <span key={label} title="Coming soon">
            {label} <em className="soon">SOON</em>
          </span>
        ))}
      </nav>
      <div className="topbar-right">
        <span>
          <span className={`status-dot ${apiUp === null ? "" : apiUp ? "ok" : "err"}`} />
          {apiUp === false ? "ENGINE OFFLINE" : "ENGINE"}
        </span>
        <span className="num clock">
          {now?.toLocaleTimeString("en-US", { hour12: false }) ?? "--:--:--"}
        </span>
      </div>
    </header>
  );
}
