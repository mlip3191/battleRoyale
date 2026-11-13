// The broadcast frame's building blocks, shared by every page.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useFocusRescue, type FocusRescue } from "./focus-rescue.ts";
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
// The crawl can be paused (WCAG 2.2.2); the button sits outside the status region so it is not
// announced with each update, and it hides when reduced motion already stops the crawl.
// The button goes away with the message. If the viewer was on it, keyboard focus stays at the
// ticker's place on the page instead of dropping to the top; a page that knows a better place
// passes its own focusGroup and moves focus itself.
export function LoadingTicker({
  message,
  focusGroup,
}: {
  message: string;
  focusGroup?: Pick<FocusRescue, "onFocus" | "onBlur">;
}) {
  const text = useRef<HTMLSpanElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const own = useFocusRescue();
  const group = focusGroup ?? own;
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (text.current) text.current.textContent = message;
    if (!message && !focusGroup) own.rescue(box.current);
  }, [message, focusGroup, own]);
  return (
    <div
      ref={box}
      className={styles.tickerBox}
      tabIndex={-1}
      onFocus={group.onFocus}
      onBlur={group.onBlur}
    >
      <div role="status" aria-live="polite">
        <div className={`${styles.ticker} ${paused ? styles.paused : ""}`}>
          <span ref={text} className={styles.tickerText} />
        </div>
      </div>
      {message && (
        <button
          type="button"
          className={styles.tickerPause}
          onClick={() => setPaused(!paused)}
        >
          {paused ? "Resume ticker" : "Pause ticker"}
        </button>
      )}
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
