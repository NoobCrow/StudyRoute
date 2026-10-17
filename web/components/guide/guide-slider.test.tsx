import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GuideScreen } from "@/components/guide/guide-screen";
import { mockGuideApi } from "@/tests/guide";
import { renderWithProviders } from "@/tests/render";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("student guide: the budget slider", () => {
  it("has a name for screen readers and starts at the typed budget", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const slider = screen.getByRole("slider", { name: /Budget slider/ });
    expect(slider).toHaveValue("200000");
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "400000");
  });

  it("moves with the amount that is typed", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const field = screen.getByLabelText("Monthly budget");
    await userEvent.clear(field);
    await userEvent.type(field, "100000");
    expect(screen.getByRole("slider", { name: /Budget slider/ })).toHaveValue("100000");
  });

  it("fills the amount box when dragged and asks for that budget in taka", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByRole("slider", { name: /Budget slider/ }), {
      target: { value: "130000" },
    });
    expect(screen.getByLabelText("Monthly budget")).toHaveValue("130000");
    await waitFor(() =>
      expect(budgetAsks().some((u) => u.searchParams.get("budget_bdt_minor") === "13000000")).toBe(
        true,
      ),
    );
    expect(window.location.search).toBe("?budget=130000");
  });

  it("clears the budget at the left end, so every city is listed without judging", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByRole("slider", { name: /Budget slider/ }), {
      target: { value: "0" },
    });
    expect(screen.getByLabelText("Monthly budget")).toHaveValue("");
    await waitFor(() =>
      expect(budgetAsks().some((u) => !u.searchParams.has("budget_bdt_minor"))).toBe(true),
    );
  });

  it("stays at its end when the typed budget is bigger than it can show", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const field = screen.getByLabelText("Monthly budget");
    await userEvent.clear(field);
    await userEvent.type(field, "900000");
    expect(screen.getByRole("slider", { name: /Budget slider/ })).toHaveValue("400000");
    expect(field).toHaveValue("900000");
  });
});
