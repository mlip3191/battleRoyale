// The shared broadcast pieces: the ticker's live region and the decorative banner option.
import { cleanup, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test } from "vitest";
import { LoadingTicker, LowerThird } from "./Broadcast.tsx";

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
