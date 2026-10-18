import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompareScreen } from "@/components/compare/compare-screen";
import { useAuth } from "@/components/providers/auth-provider";
import {
  PARENT_PERMISSIONS,
  PLAN_VIEW,
  QUOTE,
  RECIPIENT,
  STRESS,
  STUDENT_PERMISSIONS,
  corridor,
  mockApi,
  problem,
  user,
} from "@/tests/fixtures";
import { setLocation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const CORRIDORS = { items: [corridor({ account_scheme: "IBAN" })], providers: [] };
const OTHER = {
  ...RECIPIENT,
  recipient_id: "rcp_2",
  display_name: "FAIL_TEST University (synthetic)",
};

function signIn(role: "parent" | "student") {
  const permissions = role === "parent" ? PARENT_PERMISSIONS : STUDENT_PERMISSIONS;
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

function routes(recipients: unknown[], extra: Record<string, unknown> = {}) {
  return {
    "/corridors": CORRIDORS,
    "/recipients": { items: recipients },
    "/quotes": QUOTE,
    "/quotes/qte_1/stress": STRESS,
    "/planner/deadline": PLAN_VIEW,
    ...extra,
  };
}

async function getQuotesButton() {
  const button = await screen.findByRole("button", { name: "Get quotes" });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

async function getQuotes(recipients: unknown[], extra: Record<string, unknown> = {}) {
  const fetchMock = mockApi(routes(recipients, extra));
  renderWithProviders(<CompareScreen />);
  await userEvent.click(await getQuotesButton());
  await screen.findByRole("region", { name: "Provider comparison table" });
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST");

beforeEach(() => signIn("parent"));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("compare screen: the request", () => {
  it("is laid out as the design: form, charge code cards, summary and an empty quotes card", async () => {
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    expect(await screen.findByRole("heading", { name: "Compare providers" })).toBeInTheDocument();
    expect(screen.getByText("What should arrive?")).toBeInTheDocument();
    expect(screen.getByText(/We work backwards to what you send/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Charge code" })).toBeInTheDocument();
    expect(
      screen.getByText(/Check the university's own payment instructions too/),
    ).toBeInTheDocument();
    expect(screen.getByText("Your request")).toBeInTheDocument();
    expect(screen.getByText(/No quotes yet\. Press Get quotes/)).toBeInTheDocument();
  });

  it("shows the currency as a fixed prefix on the amount", async () => {
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    expect(amount).toHaveValue("10000");
    const group = amount.closest("[data-slot=input-group]") as HTMLElement;
    expect(await within(group).findByText("GBP")).toBeInTheDocument();
  });

  it("refuses characters that cannot be part of an amount", async () => {
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    await userEvent.clear(amount);
    await userEvent.type(amount, "1a2-3e4");
    expect(amount).toHaveValue("1234");
  });

  it("explains a bad amount on blur, keeps Get quotes disabled and sends nothing", async () => {
    const fetchMock = mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    await userEvent.clear(amount);
    await userEvent.type(amount, "10.505");
    await userEvent.tab();
    expect(
      await screen.findByText(/Amount: Use digits only, with at most 2 decimal places/),
    ).toBeInTheDocument();
    expect(amount).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Get quotes" })).toBeDisabled();
    expect(posted(fetchMock)).toBe(false);
  });

  it("keeps Get quotes disabled until the form is valid", async () => {
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    await userEvent.clear(amount);
    await waitFor(() => expect(screen.getByRole("button", { name: "Get quotes" })).toBeDisabled());
    await userEvent.type(amount, "2500");
    await waitFor(() => expect(screen.getByRole("button", { name: "Get quotes" })).toBeEnabled());
  });

  it("updates the summary as the form changes, and takes the send date from the engine", async () => {
    const fetchMock = mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const summary = await screen.findByRole("region", { name: "Your request" });
    expect(await within(summary).findByText("GBP 10,000")).toBeInTheDocument();
    expect(await within(summary).findByText("On track")).toBeInTheDocument();
    expect(within(summary).getByText("Thu, 22 Oct 2026")).toBeInTheDocument();
    expect(within(summary).getByText("OUR (sender pays all)")).toBeInTheDocument();
    expect(within(summary).getByText("Tuition")).toBeInTheDocument();
    expect(within(summary).getByText("United Kingdom")).toBeInTheDocument();
    expect(
      within(summary).getByText(/Indicative\. Confirm with your AD bank\./),
    ).toBeInTheDocument();

    const amount = screen.getByLabelText(/Amount the beneficiary must receive/);
    await userEvent.clear(amount);
    await userEvent.type(amount, "12500.5");
    expect(within(summary).getByText("GBP 12,500.50")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /SHA/ }));
    expect(within(summary).getByText("SHA (shared)")).toBeInTheDocument();
    const planCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/planner/deadline"),
    );
    expect(String(planCall?.[0])).toMatch(/due_date=\d{4}-\d{2}-\d{2}&country=GB$/);
  });

  it("chooses the charge code with the cards and sends it", async () => {
    const fetchMock = mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    await userEvent.click(await screen.findByRole("radio", { name: /BEN/ }));
    await userEvent.click(await getQuotesButton());
    await screen.findByRole("region", { name: "Provider comparison table" });
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/quotes"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({
      charge_code: "BEN",
    });
  });

  it("sends the amount as integer minor units with the due date", async () => {
    const fetchMock = await getQuotes([RECIPIENT]);
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/quotes"));
    const body = JSON.parse(String((call?.[1] as RequestInit).body)) as {
      target: { amount_minor: number; currency: string };
      destination_country: string;
      charge_code: string;
      due_date?: string;
    };
    expect(body.target).toEqual({ amount_minor: 1000000, currency: "GBP" });
    expect(body.destination_country).toBe("GB");
    expect(body.charge_code).toBe("OUR");
    expect(body.due_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("compare screen: the address", () => {
  it("opens a shared comparison from the URL parameters", async () => {
    setLocation(
      "/compare/",
      "destination=GB&amount=2500.50&purpose=living&chargeCode=SHA&dueDate=2099-12-31",
    );
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    expect(await screen.findByLabelText(/Amount the beneficiary must receive/)).toHaveValue(
      "2500.50",
    );
    expect(screen.getByRole("radio", { name: /SHA/ })).toBeChecked();
    expect(screen.getByRole("combobox", { name: "Purpose" })).toHaveTextContent("Living costs");
    const summary = screen.getByRole("region", { name: "Your request" });
    expect(await within(summary).findByText("GBP 2,500.50")).toBeInTheDocument();
  });

  it("ignores a bad parameter instead of breaking the form", async () => {
    setLocation("/compare/", "amount=<script>&chargeCode=ZZZ&dueDate=soon");
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    expect(await screen.findByLabelText(/Amount the beneficiary must receive/)).toHaveValue(
      "10000",
    );
    expect(screen.getByRole("radio", { name: /OUR/ })).toBeChecked();
  });

  it("writes the form into the address once the person changes it, so it can be shared", async () => {
    mockApi(routes([]));
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    expect(window.location.search).toBe("");
    await userEvent.clear(amount);
    await userEvent.type(amount, "7500");
    await userEvent.click(screen.getByRole("radio", { name: /BEN/ }));
    await waitFor(() => {
      expect(window.location.search).toContain("amount=7500");
      expect(window.location.search).toContain("chargeCode=BEN");
      expect(window.location.search).toContain("destination=GB");
    });
  });
});

describe("compare screen: the quotes", () => {
  it("shows the shortfall warning from the engine for the SHA provider", async () => {
    await getQuotes([RECIPIENT]);
    expect(screen.getByText("Short by GBP 35.00")).toBeInTheDocument();
  });

  it("marks the best provider and says it is synthetic data", async () => {
    await getQuotes([RECIPIENT]);
    const rows = screen.getAllByRole("row");
    expect(within(rows[1] as HTMLElement).getByText("Best")).toBeInTheDocument();
    expect(screen.getAllByText("Synthetic data").length).toBeGreaterThan(0);
  });

  it("moves focus to the results heading", async () => {
    await getQuotes([RECIPIENT]);
    await waitFor(() => expect(screen.getByText("Quotes")).toHaveFocus());
  });

  it("shows the problem and a Retry in the quotes card when the providers cannot be asked", async () => {
    mockApi(
      routes([], { "/quotes": problem(503, "UPSTREAM", "The synthetic providers are busy.") }),
    );
    renderWithProviders(<CompareScreen />);
    await userEvent.click(await getQuotesButton());
    expect(await screen.findByText("The synthetic providers are busy.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("never guesses the recipient when more than one exists", async () => {
    await getQuotes([OTHER, RECIPIENT]);
    const request = screen.getByRole("region", { name: "What should arrive?" });
    expect(within(request).getByRole("combobox", { name: /^Recipient/ })).toHaveTextContent(
      "Choose later",
    );
    expect(screen.getByRole("button", { name: /Create draft with/ })).toBeDisabled();
  });

  it("preselects the only recipient in the draft form when there is exactly one", async () => {
    await getQuotes([RECIPIENT]);
    const draft = screen.getByRole("region", { name: /draft/i });
    expect(within(draft).getByRole("combobox")).toHaveTextContent(RECIPIENT.display_name);
  });

  it("lets a student compare and read the breakdown but not start a payment", async () => {
    signIn("student");
    await getQuotes([RECIPIENT]);
    expect(screen.queryByRole("button", { name: /Create draft/ })).toBeNull();
    expect(screen.getByText(/Only the paying parent can create a draft/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider B (synthetic)" }),
    );
    expect(await screen.findByRole("menuitem", { name: "View breakdown" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Start payment" })).toBeNull();
  });

  it("starts a payment from a row: that provider is chosen for the draft", async () => {
    await getQuotes([RECIPIENT]);
    await userEvent.click(
      screen.getByRole("button", { name: "Actions for Provider C (synthetic)" }),
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Start payment" }));
    const rows = screen.getAllByRole("row");
    expect(within(rows[2] as HTMLElement).getByText("Selected")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).queryByText("Selected")).toBeNull();
  });

  it("shows the currency-drop stress test under the quote", async () => {
    await getQuotes([RECIPIENT]);
    expect(await screen.findByText("Currency-drop stress test")).toBeInTheDocument();
    expect(await screen.findByText(/5% more taka/)).toBeInTheDocument();
  });
});
