import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/AuthContext";
import { PARENT_PERMISSIONS, QUOTE, RECIPIENT, STUDENT_PERMISSIONS, mockApi, user } from "../test/fixtures";
import { CompareScreen } from "./Compare";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const CORRIDORS = {
  items: [{ country: "GB", name: "United Kingdom", currency: "GBP", account_scheme: "IBAN", host_rail: "x", mid_rate: "160" }],
  providers: [],
};
const OTHER = { ...RECIPIENT, recipient_id: "rcp_2", display_name: "FAIL_TEST University (synthetic)" };

function signIn(role: "parent" | "student") {
  const permissions = role === "parent" ? PARENT_PERMISSIONS : STUDENT_PERMISSIONS;
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
}

async function getQuotes(recipients: unknown[]) {
  mockApi({ "/corridors": CORRIDORS, "/recipients": { items: recipients }, "/quotes": QUOTE });
  render(<MemoryRouter><CompareScreen /></MemoryRouter>);
  await screen.findByRole("option", { name: /United Kingdom/ });
  await userEvent.click(screen.getByRole("button", { name: "Get quotes" }));
  await screen.findByText("Lowest cost");
}

beforeEach(() => signIn("parent"));
afterEach(() => vi.unstubAllGlobals());

describe("compare screen", () => {
  it("shows the shortfall warning from the engine for the SHA provider", async () => {
    await getQuotes([RECIPIENT]);
    expect(screen.getByRole("alert", { name: "" })).toHaveTextContent("Short by GBP 35.00");
  });

  it("never guesses the recipient when more than one exists", async () => {
    await getQuotes([OTHER, RECIPIENT]);
    const select = screen.getByLabelText("Recipient") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(screen.getByRole("button", { name: /Create draft/ })).toBeDisabled();
  });

  it("preselects the only recipient when there is exactly one", async () => {
    await getQuotes([RECIPIENT]);
    expect((screen.getByLabelText("Recipient") as HTMLSelectElement).value).toBe("rcp_1");
  });

  it("lets a student compare but not create a draft", async () => {
    signIn("student");
    await getQuotes([RECIPIENT]);
    expect(screen.queryByRole("button", { name: /Create draft/ })).toBeNull();
    expect(screen.getByText(/Only the paying parent can create a draft/)).toBeInTheDocument();
  });

  it("explains the three charge codes and recommends OUR for tuition", async () => {
    mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [] } });
    render(<MemoryRouter><CompareScreen /></MemoryRouter>);
    await userEvent.click(await screen.findByText(/Which charge code should I choose/));
    expect(screen.getByText(/recommended for tuition/)).toBeInTheDocument();
  });
});
