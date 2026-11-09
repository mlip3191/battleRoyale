import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "./Home.tsx";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows the backend status from /api/health", async () => {
  const fetchMock = vi.fn().mockResolvedValue(Response.json({ status: "ok" }));
  vi.stubGlobal("fetch", fetchMock);

  render(<Home />);

  expect(await screen.findByText("Backend: ok")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/health");
});
