import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "./components/ThemeToggle";
import { applyTheme, nextTheme, readTheme, saveTheme } from "./theme";

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("theme", () => {
  it("cycles Auto, Light, Dark and back", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });

  it("applies a choice to the page and clears it for Auto", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    applyTheme("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("remembers Light and Dark, and treats anything else as Auto", () => {
    saveTheme("light");
    expect(readTheme()).toBe("light");
    localStorage.setItem("sr.theme", "neon");
    expect(readTheme()).toBe("system");
    saveTheme("system");
    expect(localStorage.getItem("sr.theme")).toBeNull();
  });

  it("the toggle button shows the choice, applies it and saves it", async () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Theme: Auto" });
    await userEvent.click(button);
    expect(screen.getByRole("button", { name: "Theme: Light" })).toBeInTheDocument();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("sr.theme")).toBe("light");
  });
});
