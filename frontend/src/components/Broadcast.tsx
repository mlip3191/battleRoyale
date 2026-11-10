// The broadcast frame's building blocks, shared by every page.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import styles from "./broadcast.module.css";

// Top bar with the show's name; the logo links home.
export function Header() {
  return (
    <header className={styles.header}>
      <Link to="/" className={styles.logo}>
        BATTLE ROYALE
      </Link>
      <span className={styles.live} aria-hidden="true">
        ● LIVE
      </span>
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

// A friendly error box instead of a blank screen.
export function ErrorPanel({
  title = "Technical difficulties",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <section className={styles.error} role="alert">
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}
