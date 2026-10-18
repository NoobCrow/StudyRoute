import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeMenu } from "@/components/layout/theme-menu";

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  document.documentElement.classList.remove("theme-fade");
});

describe("ThemeMenu", () => {
  it("cross-fades the colours for a moment when the theme changes, then stops", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ThemeMenu />);
    await user.click(screen.getByRole("button", { name: /Theme/ }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Dark" }));

    expect(document.documentElement).toHaveClass("theme-fade");
    await vi.advanceTimersByTimeAsync(500);
    expect(document.documentElement).not.toHaveClass("theme-fade");
  });
});
