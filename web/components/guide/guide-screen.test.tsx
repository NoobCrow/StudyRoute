import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GuideScreen } from "@/components/guide/guide-screen";
import { mockGuideApi } from "@/tests/guide";
import { setLocation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("student guide: the budget", () => {
  it("asks for every city with the default budget and lists them cheapest first", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    const table = await screen.findByRole("table", {
      name: "Student cities, cheapest month first",
    });
    const names = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[0]?.textContent);
    expect(names).toEqual([
      "Johor BahruMalaysia",
      "ManchesterUnited Kingdom",
      "LondonUnited Kingdom",
    ]);
    const first = budgetAsks()[0]!;
    expect(first.searchParams.get("housing")).toBe("shared");
    expect(first.searchParams.get("budget_bdt_minor")).toBe("20000000");
    expect(first.searchParams.has("country")).toBe(false);
  });

  it("says how many cities fit and marks each with text and an icon, never colour alone", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    expect(await screen.findByText("2 of 3 cities")).toBeInTheDocument();
    expect(screen.getByText(/fit BDT 200,000.00 a month/)).toBeInTheDocument();
    expect(screen.getByText("Fits, BDT 8,800.00 to spare")).toBeInTheDocument();
    expect(screen.getByText("Short by BDT 56,800.00")).toBeInTheDocument();
    expect(screen.getByText(/Cheapest: Johor Bahru, BDT 40,820.00/)).toBeInTheDocument();
  });

  it("labels the figures as invented and not verified, with the source as plain text", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("Invented figures")).toBeInTheDocument();
    expect(screen.getByText(/not a survey/)).toBeInTheDocument();
    expect(screen.getByText(/Indicative. Confirm with your AD bank./)).toBeInTheDocument();
    const source = screen.getByText("https://example.org/replace-with-cost-of-living-source");
    expect(source.tagName).toBe("CODE");
    expect(source.closest("a")).toBeNull();
  });

  it("asks again, in taka, 300 ms after the budget is typed", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const field = screen.getByLabelText("Monthly budget");
    await userEvent.clear(field);
    await userEvent.type(field, "150,000");
    await waitFor(() =>
      expect(budgetAsks().some((u) => u.searchParams.get("budget_bdt_minor") === "15000000")).toBe(
        true,
      ),
    );
    expect(window.location.search).toBe("?budget=150000");
  });

  it("refuses a budget with too many decimals instead of asking for it", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const field = screen.getByLabelText("Monthly budget");
    await userEvent.clear(field);
    await userEvent.type(field, "1.234");
    expect(
      await screen.findByText("Use digits only, with at most 2 decimal places."),
    ).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    await new Promise((resolve) => setTimeout(resolve, 450));
    expect(budgetAsks().every((u) => u.searchParams.get("budget_bdt_minor") !== "123")).toBe(true);
  });

  it("lists every city without judging them when the budget is cleared", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    await userEvent.clear(screen.getByLabelText("Monthly budget"));
    await waitFor(() =>
      expect(budgetAsks().some((u) => !u.searchParams.has("budget_bdt_minor"))).toBe(true),
    );
    expect(await screen.findByText(/Enter a monthly budget to see which fit/)).toBeInTheDocument();
    expect(screen.queryByText("Your budget")).toBeNull();
    expect(window.location.search).toBe("?budget=");
  });

  it("asks for a studio when the kind of housing is changed", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("combobox", { name: "Where you would live" }));
    await userEvent.click(await screen.findByRole("option", { name: "Your own studio" }));
    await waitFor(() =>
      expect(budgetAsks().some((u) => u.searchParams.get("housing") === "studio")).toBe(true),
    );
    expect(await screen.findByText("Your own studio, a month")).toBeInTheDocument();
  });

  it("narrows to one country from the countries the answer lists", async () => {
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("combobox", { name: "Country" }));
    await userEvent.click(await screen.findByRole("option", { name: "Malaysia" }));
    await waitFor(() =>
      expect(budgetAsks().some((u) => u.searchParams.get("country") === "MY")).toBe(true),
    );
    expect(window.location.search).toContain("country=MY");
  });

  it("opens a city's month line by line from the engine's own figures", async () => {
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Manchester" }));
    const sheet = await screen.findByRole("dialog", { name: "Manchester, United Kingdom" });
    expect(within(sheet).getByText("Food and groceries")).toBeInTheDocument();
    expect(within(sheet).getByText("GBP 1,195.00")).toBeInTheDocument();
    expect(within(sheet).getByText("In taka at 160.000000 BDT per GBP")).toBeInTheDocument();
    expect(within(sheet).getByText("Fits, BDT 8,800.00 to spare")).toBeInTheDocument();
    expect(
      within(sheet).getByText(/against your budget of BDT 200,000.00 a month/),
    ).toBeInTheDocument();
  });

  it("says what went wrong and offers a Retry that works", async () => {
    mockGuideApi({ budgetFails: true });
    renderWithProviders(<GuideScreen />);
    expect(await screen.findByText("The figures are not available.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("reads a shared link: the budget, the housing and the country", async () => {
    setLocation("/guide/", "budget=90000&housing=studio&country=GB");
    const { budgetAsks } = mockGuideApi();
    renderWithProviders(<GuideScreen />);
    await screen.findByRole("table");
    const asked = budgetAsks()[0]!;
    expect(asked.searchParams.get("budget_bdt_minor")).toBe("9000000");
    expect(asked.searchParams.get("housing")).toBe("studio");
    expect(asked.searchParams.get("country")).toBe("GB");
    expect(screen.getByLabelText("Monthly budget")).toHaveValue("90000");
  });
});

describe("student guide: the arrival checklist", () => {
  async function openArrival() {
    renderWithProviders(<GuideScreen />);
    await userEvent.click(await screen.findByRole("tab", { name: "Arrival checklist" }));
    return await screen.findByRole("region", { name: /Your arrival checklist/ });
  }

  it("lists the steps by stage with a hint on each", async () => {
    mockGuideApi();
    const card = await openArrival();
    expect(within(card).getByRole("heading", { name: "Before you fly" })).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "In your first week" })).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "In your first month" })).toBeInTheDocument();
    expect(within(card).getAllByRole("checkbox")).toHaveLength(4);
    expect(within(card).getByLabelText("Open a student bank account")).toHaveAccessibleDescription(
      "Take your passport.",
    );
    expect(within(card).getByText("0 of 4 done")).toBeInTheDocument();
    expect(screen.getByText("Not verified")).toBeInTheDocument();
  });

  it("counts the ticks, keeps them for the country and clears them on request", async () => {
    mockGuideApi();
    const card = await openArrival();
    await userEvent.click(within(card).getByLabelText("Open a student bank account"));
    await userEvent.click(within(card).getByLabelText("Know how much you may work"));
    expect(within(card).getByText("2 of 4 done")).toBeInTheDocument();
    expect(within(card).getByRole("progressbar", { name: "Steps done" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(JSON.parse(localStorage.getItem("studyroute.arrival.GB") ?? "[]")).toEqual([
      "student_account",
      "work_rules",
    ]);
    await userEvent.click(within(card).getByRole("button", { name: "Clear ticks" }));
    expect(within(card).getByText("0 of 4 done")).toBeInTheDocument();
    expect(localStorage.getItem("studyroute.arrival.GB")).toBeNull();
  });

  it("remembers earlier ticks when the page is opened again", async () => {
    localStorage.setItem(
      "studyroute.arrival.GB",
      JSON.stringify(["accommodation", "no_longer_a_step"]),
    );
    mockGuideApi();
    const card = await openArrival();
    expect(within(card).getByLabelText("Book a place to live before you fly")).toBeChecked();
    expect(within(card).getByText("1 of 4 done")).toBeInTheDocument();
  });

  it("says so when a country only has the general list", async () => {
    setLocation("/guide/", "tab=arrival&arrival=FR");
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    expect(await screen.findByText(/This is a general list/)).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Your arrival checklist: France" }),
    ).toBeInTheDocument();
  });

  it("opens straight on this tab from a shared link and keeps the address up to date", async () => {
    setLocation("/guide/", "tab=arrival");
    mockGuideApi();
    renderWithProviders(<GuideScreen />);
    expect(
      await screen.findByRole("region", { name: /Your arrival checklist/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Arrival checklist" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() => expect(window.location.search).toBe("?tab=arrival"));
  });
});
