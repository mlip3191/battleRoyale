// The broadcast frame's building blocks, shared by every page.
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import styles from "./broadcast.module.css";

// Class for text only screen readers see (e.g. a page heading the design doesn't show).
export const srOnly = styles.srOnly;

// Top bar with the show's name; the logo links home. "LIVE" shows only during a broadcast.
export function Header() {
  const onAir = /^\/battle\/[^/]+\/?$/.test(useLocation().pathname);
  return (
    <header className={styles.header}>
      <Link to="/" className={styles.logo}>
        BATTLE ROYALE
      </Link>
      {onAir && (
        <span className={styles.live} aria-hidden="true">
          ● LIVE
        </span>
      )}
    </header>
  );
}

// A TV-style name banner along the bottom third of the screen.
export function LowerThird({ children }: { children: ReactNode }) {
  return <div className={styles.lowerThird}>{children}</div>;
}

// A crawling news ticker shown while research runs; screen readers hear each update.
export function LoadingTicker({ message }: { message: string }) {
  return (
    <div className={styles.ticker} role="status" aria-live="polite">
      <span className={styles.tickerText}>{message}</span>
    </div>
  );
}

// A friendly error box instead of a blank screen. Pages with no other heading pass level 1.
export function ErrorPanel({
  title = "Technical difficulties",
  message,
  level = 2,
}: {
  title?: string;
  message: string;
  level?: 1 | 2;
}) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <section className={styles.error} role="alert">
      <Heading>{title}</Heading>
      <p>{message}</p>
    </section>
  );
}
