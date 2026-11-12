// The shared broadcast pieces: the ticker's live region and the decorative banner option.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";
import { LoadingTicker, LowerThird } from "./Broadcast.tsx";
import css from "./broadcast.module.css?raw";

afterEach(cleanup);

test("the ticker's status region starts empty, so the first message is announced", () => {
  const html = renderToStaticMarkup(<LoadingTicker message="First update" />);
  expect(html).toContain('role="status"');
  expect(html).not.toContain("First update");
});

test("the ticker keeps one status region and only changes its text", () => {
  const { rerender } = render(<LoadingTicker message="First update" />);
  const region = screen.getByRole("status");
  expect(region.textContent).toBe("First update");
  rerender(<LoadingTicker message="Second update" />);
  expect(screen.getByRole("status")).toBe(region);
  expect(region.textContent).toBe("Second update");
  rerender(<LoadingTicker message="" />);
  expect(screen.getByRole("status")).toBe(region);
  expect(region.textContent).toBe("");
});

test("a decorative banner is hidden from screen readers; a normal one is not", () => {
  render(
    <>
      <LowerThird decorative>Shown only</LowerThird>
      <LowerThird>Heard too</LowerThird>
    </>,
  );
  expect(screen.getByText("Shown only").getAttribute("aria-hidden")).toBe(
    "true",
  );
  expect(screen.getByText("Heard too").hasAttribute("aria-hidden")).toBe(false);
});

test("the moving ticker can be paused and resumed (WCAG 2.2.2), outside the status region", () => {
  const { container } = render(<LoadingTicker message="Researching" />);
  const pause = screen.getByRole("button", { name: "Pause ticker" });
  expect(screen.getByRole("status").contains(pause)).toBe(false);
  fireEvent.click(pause);
  expect(container.querySelector('[class*="paused"]')).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Resume ticker" }));
  expect(container.querySelector('[class*="paused"]')).toBeNull();
});

test("an empty ticker has no pause button", () => {
  render(<LoadingTicker message="" />);
  expect(screen.queryByRole("button")).toBeNull();
});

test("keyboard: the Pause ticker button going away leaves focus at the ticker, not the top of the page", () => {
  const { container, rerender } = render(
    <LoadingTicker message="Researching" />,
  );
  screen.getByRole("button", { name: "Pause ticker" }).focus();
  rerender(<LoadingTicker message="" />);
  expect(screen.queryByRole("button")).toBeNull();
  expect(document.activeElement).toBe(container.firstElementChild);
  expect(container.firstElementChild!.getAttribute("tabindex")).toBe("-1");
});

test("keyboard: the ticker ending moves nothing when the viewer wasn't on its button", () => {
  const { rerender } = render(<LoadingTicker message="Researching" />);
  rerender(<LoadingTicker message="" />);
  expect(document.activeElement).toBe(document.body);
});

test("keyboard: a page that passes its own focus group is left to move focus itself", () => {
  const group = { onFocus: vi.fn(), onBlur: vi.fn() };
  const { rerender } = render(
    <LoadingTicker message="Researching" focusGroup={group} />,
  );
  screen.getByRole("button", { name: "Pause ticker" }).focus();
  expect(group.onFocus).toHaveBeenCalled();
  rerender(<LoadingTicker message="" focusGroup={group} />);
  expect(document.activeElement).toBe(document.body);
});

test("reduced motion: the ticker wraps instead of crawling, and its pause button hides", () => {
  const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion"));
  expect(reduced).toMatch(/\.ticker\s*{\s*white-space:\s*normal/);
  expect(reduced).toMatch(/\.tickerPause\s*{\s*display:\s*none/);
  expect(css).toMatch(
    /\.paused \.tickerText\s*{\s*animation-play-state:\s*paused/,
  );
});
