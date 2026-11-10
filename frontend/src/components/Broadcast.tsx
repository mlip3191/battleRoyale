// The broadcast frame's building blocks, shared by every page.
import { useEffect, useRef, type ReactNode } from "react";
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
// Pass decorative when a heading already says the same thing, so screen readers hear it once.
export function LowerThird({
  children,
  decorative = false,
}: {
  children: ReactNode;
  decorative?: boolean;
}) {
  return (
    <div className={styles.lowerThird} aria-hidden={decorative || undefined}>
      {children}
    </div>
  );
}

// A crawling news ticker shown while research runs; screen readers hear each update.
// The status region is always rendered and starts empty; only its text changes, written after
// mount, so screen readers already know the region when the first message arrives.
// An empty message hides the ticker bar but keeps the region in place.
export function LoadingTicker({ message }: { message: string }) {
  const text = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (text.current) text.current.textContent = message;
  }, [message]);
  return (
    <div role="status" aria-live="polite">
      <div className={styles.ticker}>
        <span ref={text} className={styles.tickerText} />
      </div>
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
