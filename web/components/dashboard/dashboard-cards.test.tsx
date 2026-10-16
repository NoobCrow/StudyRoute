import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KycCard } from "@/components/dashboard/kyc-card";
import { PlannerCard } from "@/components/dashboard/planner-card";
import { RateCard } from "@/components/dashboard/rate-card";
import { RunwayCard } from "@/components/dashboard/runway-card";
import { SendPlanCard } from "@/components/dashboard/send-plan-card";
import { YourDataCard } from "@/components/dashboard/your-data-card";
import { useAuth } from "@/components/providers/auth-provider";
import type { PlanView, RateHistory, RunwayView } from "@/lib/api/types";
import {
  KYC,
  PARENT_PERMISSIONS,
  SEND_PLAN,
  corridor,
  mockApi,
  problem,
  user,
} from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const CORRIDORS = [
  corridor(),
  corridor({
    country: "JP",
    name: "Japan",
    currency: "JPY",
    exponent: 0,
    sample_amount: "1500000",
  }),
];

const PLAN: PlanView = {
  due_date: "2026-10-28",
  latest_send_date: "2026-10-20",
  recommended_send_date: "2026-10-19",
  earliest_send_date: "2026-10-16",
  status: "ON_TRACK",
  days_until_latest_send: 4,
  settlement_business_days: 3,
  buffer_days: 2,
  bank_cutoff_local: "15:00",
  skipped_days: [{ date: "2026-10-17", reasons: ["Weekend in Bangladesh"] }],
  warnings: [{ code: "HOLIDAY_OVERLAP", message: "A public holiday falls in the window." }],
  indicative: "Indicative. Confirm with your AD bank.",
  destination_country: "GB",
};

const RUNWAY: RunwayView = {
  display: {
    amount: "GBP 5,000.00",
    monthly_cost: "GBP 1,200.00",
    covers: "4.1 months",
    full_months: "4",
    leftover: "GBP 200.00",
  },
  monthly_cost_usd_equivalent: "USD 1,560.00",
  reference: {
    label: "Reference",
    value: "GBP 1,300.00",
    verified: false,
    badge: "NOT_VERIFIED",
    note: "Not an official figure.",
  },
};

const HISTORY: RateHistory = {
  currency: "GBP",
  source: "synthetic",
  disclaimer: "Synthetic data. Not a forecast. Indicative. Confirm with your AD bank.",
  points: [
    { date: "2026-10-12", rate: "159.500000" },
    { date: "2026-10-13", rate: "160.500000" },
    { date: "2026-10-14", rate: "161.000000" },
  ],
  hint: {
    kind: "WAIT_MAY_HELP",
    today: "161.000000",
    average: "160.333333",
    gap_pct: "0.42",
    days: 3,
    message: "Today is a little above the average.",
  },
};

function signIn(role: "parent" | "admin" = "parent") {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, PARENT_PERMISSIONS),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn().mockResolvedValue(undefined),
  });
}

beforeEach(() => signIn());
afterEach(() => vi.unstubAllGlobals());

describe("PlannerCard (deadline)", () => {
  it("shows the engine's dates and the status, and does not work out a date itself", async () => {
    const fetchMock = mockApi({ "/planner/deadline": PLAN });
    renderWithProviders(<PlannerCard corridors={CORRIDORS} />);
    expect(await screen.findByText("On track")).toBeInTheDocument();
    expect(screen.getByText(/4 calendar days until the latest send date/)).toBeInTheDocument();
    expect(screen.getByText("Tue, 20 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText("Mon, 19 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText(/after the 15:00 Dhaka/)).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(
      /\/planner\/deadline\?due_date=\d{4}-\d{2}-\d{2}&country=GB$/,
    );
  });

  it("draws fifteen days around the deadline with a text label on each", async () => {
    mockApi({ "/planner/deadline": PLAN });
    renderWithProviders(<PlannerCard corridors={CORRIDORS} />);
    const strip = await screen.findByRole("list", { name: "Fifteen days around the deadline" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(15);
    expect(
      within(strip)
        .getAllByRole("img")
        .every((day) => (day.getAttribute("aria-label") ?? "").length > 0),
    ).toBe(true);
    expect(screen.getByRole("list", { name: "Legend" })).toBeInTheDocument();
  });

  it("says plainly when it is too late for normal settlement", async () => {
    mockApi({ "/planner/deadline": { ...PLAN, status: "LATE", days_until_latest_send: -2 } });
    renderWithProviders(<PlannerCard corridors={CORRIDORS} />);
    expect(await screen.findByText("Too late for normal settlement")).toBeInTheDocument();
  });

  it("lists the warnings and the skipped days, and always says it is indicative", async () => {
    mockApi({ "/planner/deadline": PLAN });
    renderWithProviders(<PlannerCard corridors={CORRIDORS} />);
    expect(await screen.findByText("A public holiday falls in the window.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("1 non-working days skipped"));
    expect(screen.getByText(/Weekend in Bangladesh/)).toBeInTheDocument();
    expect(screen.getByText("Indicative.")).toBeInTheDocument();
    expect(screen.getByText(/Confirm with your AD bank\./)).toBeInTheDocument();
  });

  it("shows the server's reason with a Retry when the plan cannot be made", async () => {
    mockApi({
      "/planner/deadline": problem(422, "VALIDATION_ERROR", "The due date is in the past."),
    });
    renderWithProviders(<PlannerCard corridors={CORRIDORS} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The due date is in the past.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("RunwayCard", () => {
  it("calculates on load with integer minor units and shows what the engine answered", async () => {
    const fetchMock = mockApi({ "/planner/runway": RUNWAY });
    renderWithProviders(<RunwayCard corridors={CORRIDORS} />);
    expect(await screen.findByText("months of living costs covered")).toBeInTheDocument();
    expect(screen.getByText("4.1")).toBeInTheDocument();
    expect(
      screen.getByText(/Based on GBP 5,000.00 sent and GBP 1,200.00 a month\./),
    ).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/planner/runway?amount_minor=500000&monthly_cost_minor=120000&currency=GBP",
    );
  });

  it("marks the reference figure as not verified", async () => {
    mockApi({ "/planner/runway": RUNWAY });
    renderWithProviders(<RunwayCard corridors={CORRIDORS} />);
    expect(await screen.findByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("Not an official figure.")).toBeInTheDocument();
  });

  it("recalculates from the typed amount, converted to minor units without floating point", async () => {
    const fetchMock = mockApi({ "/planner/runway": RUNWAY });
    renderWithProviders(<RunwayCard corridors={CORRIDORS} />);
    await screen.findByText("months of living costs covered");
    const amount = screen.getByLabelText("Amount sent");
    await userEvent.clear(amount);
    await userEvent.type(amount, "7,250.10");
    await userEvent.click(screen.getByRole("button", { name: "Calculate runway" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("amount_minor=725010&");
  });

  it("explains a bad amount instead of sending it", async () => {
    const fetchMock = mockApi({ "/planner/runway": RUNWAY });
    renderWithProviders(<RunwayCard corridors={CORRIDORS} />);
    await screen.findByText("months of living costs covered");
    const amount = screen.getByLabelText("Amount sent");
    await userEvent.clear(amount);
    await userEvent.type(amount, "lots");
    await userEvent.click(screen.getByRole("button", { name: "Calculate runway" }));
    expect(await screen.findByText(/Amount:/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("SendPlanCard", () => {
  it("keeps the comparison hidden until the person asks for it", async () => {
    const fetchMock = mockApi({ "/planner/send-plan": SEND_PLAN });
    renderWithProviders(<SendPlanCard corridors={CORRIDORS} />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("region", { name: "Send plan comparison table" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Compare ways to send" }));
    expect(
      await screen.findByRole("region", { name: "Send plan comparison table" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cheapest on paper")).toBeInTheDocument();
  });

  it("asks the engine in minor units with the charge code", async () => {
    const fetchMock = mockApi({ "/planner/send-plan": SEND_PLAN });
    renderWithProviders(<SendPlanCard corridors={CORRIDORS} />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/planner/send-plan?monthly_minor=100000&months=12&currency=GBP&charge_code=OUR",
    );
  });

  it("shows how many times the fixed fees are paid as the months change", async () => {
    mockApi({ "/planner/send-plan": SEND_PLAN });
    renderWithProviders(<SendPlanCard corridors={CORRIDORS} />);
    expect(screen.getByText("12 transfers")).toBeInTheDocument();
    const months = screen.getByLabelText("Months to cover");
    await userEvent.clear(months);
    await userEvent.type(months, "9");
    expect(screen.getByText("9 transfers")).toBeInTheDocument();
  });

  it("rejects a months value that is not a whole number", async () => {
    const fetchMock = mockApi({ "/planner/send-plan": SEND_PLAN });
    renderWithProviders(<SendPlanCard corridors={CORRIDORS} />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const months = screen.getByLabelText("Months to cover");
    await userEvent.clear(months);
    await userEvent.type(months, "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Compare ways to send" }));
    expect(
      await screen.findByText("Months: enter a whole number from 1 to 60."),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("RateCard", () => {
  const selector = <span>selector</span>;

  it("shows the hint in words with the numbers behind it, and says it is synthetic", async () => {
    mockApi({ "/rates/history": HISTORY });
    renderWithProviders(<RateCard currency="GBP" selector={selector} />);
    expect(await screen.findByText("Waiting may help")).toBeInTheDocument();
    expect(screen.getByText("0.42% vs the 3-day average")).toBeInTheDocument();
    expect(screen.getByText("Today is a little above the average.")).toBeInTheDocument();
    expect(screen.getByText("Synthetic data")).toBeInTheDocument();
    expect(screen.getByText(HISTORY.disclaimer)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /GBP synthetic rate over 3 days/ })).toBeInTheDocument();
  });

  it("puts the values in a table for anyone who cannot read the chart", async () => {
    mockApi({ "/rates/history": HISTORY });
    renderWithProviders(<RateCard currency="GBP" selector={selector} />);
    await userEvent.click(await screen.findByText("Show the 3 values as a table"));
    expect(screen.getByRole("cell", { name: "159.500000" })).toBeInTheDocument();
  });

  it("raises an alert when today's rate is at or below the target, and remembers it in this browser", async () => {
    mockApi({ "/rates/history": HISTORY });
    renderWithProviders(<RateCard currency="GBP" selector={selector} />);
    const target = await screen.findByLabelText(/Rate alert/);
    await userEvent.type(target, "160");
    expect(screen.queryByText(/Alert: today's synthetic rate/)).toBeNull();
    await userEvent.clear(target);
    await userEvent.type(target, "162");
    expect(
      await screen.findByText(/Alert: today's synthetic rate 161.000000 is at or below your 162\./),
    ).toBeInTheDocument();
    await vi.waitFor(() => expect(localStorage.getItem("sr.rate-alert.GBP")).toBe("162"));
  });

  it("brings back a saved alert for that currency", async () => {
    localStorage.setItem("sr.rate-alert.GBP", "165");
    mockApi({ "/rates/history": HISTORY });
    renderWithProviders(<RateCard currency="GBP" selector={selector} />);
    expect(await screen.findByLabelText(/Rate alert/)).toHaveValue("165");
  });

  it("rejects a target that is not a number", async () => {
    mockApi({ "/rates/history": HISTORY });
    renderWithProviders(<RateCard currency="GBP" selector={selector} />);
    await userEvent.type(await screen.findByLabelText(/Rate alert/), "cheap");
    expect(await screen.findByText("Use digits and one decimal point.")).toBeInTheDocument();
    expect(localStorage.getItem("sr.rate-alert.GBP")).toBeNull();
  });
});

describe("KycCard", () => {
  it("offers to submit the mock documents when they are missing, and reloads the user", async () => {
    const reloadUser = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      user: user("parent", PARENT_PERMISSIONS),
      ready: true,
      login: vi.fn(),
      logout: vi.fn(),
      reloadUser,
    });
    const needs = {
      ...KYC,
      status: "NEEDS_DOCUMENTS" as const,
      message: "Documents are missing.",
      required_documents: [{ key: "passport", label: "Passport (synthetic)" }],
    };
    const fetchMock = mockApi({ "/kyc/status": needs, "/kyc/mock-submit": { ok: true } });
    renderWithProviders(<KycCard />);
    expect(await screen.findByText("KYC needs documents (simulated)")).toBeInTheDocument();
    expect(screen.getByText(/Approval is blocked until this is verified/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit mock documents" }));
    await vi.waitFor(() => expect(reloadUser).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/kyc/mock-submit"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      documents: ["passport"],
    });
  });

  it("shows a verified badge and no warning once the check is done", async () => {
    mockApi({ "/kyc/status": { ...KYC, status: "VERIFIED", message: "Verified (simulated)." } });
    renderWithProviders(<KycCard />);
    expect(await screen.findByText("KYC verified (simulated)")).toBeInTheDocument();
    expect(screen.queryByText(/Approval is blocked/)).toBeNull();
  });

  it("lets a reviewer set the status of a payer, and nobody else", async () => {
    signIn("admin");
    const fetchMock = mockApi({ "/kyc/status": KYC, "/kyc/mock-review": { ok: true } });
    renderWithProviders(<KycCard payerId="usr_parent" />);
    await userEvent.click(await screen.findByRole("button", { name: "VERIFIED" }));
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/kyc/mock-review"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      user_id: "usr_parent",
      status: "VERIFIED",
    });
  });

  it("asks a reviewer for a payer id before showing anything", async () => {
    signIn("admin");
    const fetchMock = mockApi({});
    renderWithProviders(<KycCard />);
    expect(
      await screen.findByText("Enter a payer user id to review their simulated KYC."),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("YourDataCard", () => {
  it("asks first, and sends nothing until the person confirms", async () => {
    const fetchMock = mockApi({ "/me/reset": { reset: true, deleted: { payments: 2 } } });
    renderWithProviders(<YourDataCard />);
    await userEvent.click(screen.getByRole("button", { name: "Reset my data" }));
    expect(
      await screen.findByRole("alertdialog", { name: "Delete all of your data?" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete my data" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/v1/me/reset");
  });

  it("lets the person back out", async () => {
    const fetchMock = mockApi({});
    renderWithProviders(<YourDataCard />);
    await userEvent.click(screen.getByRole("button", { name: "Reset my data" }));
    await userEvent.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("keeps the dialog open and shows the reason when the reset fails", async () => {
    mockApi({ "/me/reset": problem(500, "SERVER_ERROR", "Could not reset.") });
    renderWithProviders(<YourDataCard />);
    await userEvent.click(screen.getByRole("button", { name: "Reset my data" }));
    await userEvent.click(await screen.findByRole("button", { name: "Yes, delete my data" }));
    expect(await screen.findByText("Could not reset.")).toBeInTheDocument();
  });
});
