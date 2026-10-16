import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompareScreen } from "@/components/compare/compare-screen";
import { useAuth } from "@/components/providers/auth-provider";
import {
  PARENT_PERMISSIONS,
  QUOTE,
  RECIPIENT,
  STRESS,
  STUDENT_PERMISSIONS,
  corridor,
  mockApi,
  user,
} from "@/tests/fixtures";
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

async function getQuotes(recipients: unknown[], extra: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    "/corridors": CORRIDORS,
    "/recipients": { items: recipients },
    "/quotes": QUOTE,
    "/quotes/qte_1/stress": STRESS,
    ...extra,
  });
  renderWithProviders(<CompareScreen />);
  await userEvent.click(await screen.findByRole("button", { name: "Get quotes" }));
  await screen.findByText("Lowest cost");
  return fetchMock;
}

beforeEach(() => signIn("parent"));
afterEach(() => vi.unstubAllGlobals());

describe("compare screen", () => {
  it("shows the shortfall warning from the engine for the SHA provider", async () => {
    await getQuotes([RECIPIENT]);
    expect(screen.getByText("Short by GBP 35.00")).toBeInTheDocument();
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

  it("never guesses the recipient when more than one exists", async () => {
    await getQuotes([OTHER, RECIPIENT]);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      "Choose a recipient",
    );
    expect(screen.getByRole("button", { name: /Create draft/ })).toBeDisabled();
  });

  it("preselects the only recipient when there is exactly one", async () => {
    await getQuotes([RECIPIENT]);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      RECIPIENT.display_name,
    );
  });

  it("lets a student compare but not create a draft", async () => {
    signIn("student");
    await getQuotes([RECIPIENT]);
    expect(screen.queryByRole("button", { name: /Create draft/ })).toBeNull();
    expect(screen.getByText(/Only the paying parent can create a draft/)).toBeInTheDocument();
  });

  it("shows the currency-drop stress test under the quote", async () => {
    await getQuotes([RECIPIENT]);
    expect(await screen.findByText("Currency-drop stress test")).toBeInTheDocument();
    expect(await screen.findByText(/5% more taka/)).toBeInTheDocument();
  });

  it("explains a bad amount before anything is sent", async () => {
    const fetchMock = mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [] } });
    renderWithProviders(<CompareScreen />);
    const amount = await screen.findByLabelText(/Amount the beneficiary must receive/);
    await userEvent.clear(amount);
    await userEvent.type(amount, "ten");
    await userEvent.click(screen.getByRole("button", { name: "Get quotes" }));
    expect(await screen.findByText(/Amount: Use digits only/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST"),
    ).toBe(false);
  });

  it("explains the three charge codes and recommends OUR for tuition", async () => {
    mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [] } });
    renderWithProviders(<CompareScreen />);
    await userEvent.click(await screen.findByText(/Which charge code should I choose/));
    expect(screen.getByText(/recommended for tuition/)).toBeInTheDocument();
  });
});
