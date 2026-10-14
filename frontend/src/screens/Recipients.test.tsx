import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/AuthContext";
import { PARENT_PERMISSIONS, RECIPIENT, mockApi, user } from "../test/fixtures";
import { RecipientsScreen } from "./Recipients";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const CORRIDORS = {
  items: [{ country: "GB", name: "United Kingdom", currency: "GBP", account_scheme: "IBAN_OR_UK_DOMESTIC", host_rail: "x", mid_rate: "160" }],
  providers: [],
};
const SCRIPT = '<script>window.__pwned = true</script><img src=x onerror="window.__pwned=true">';

beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({
    user: user("parent", PARENT_PERMISSIONS), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("recipients screen", () => {
  it("T23: a script tag in a recipient name is shown as plain text and never runs", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [{ ...RECIPIENT, display_name: SCRIPT }] },
      "/health": { mode: "sandbox" },
    });
    const { container } = render(<MemoryRouter><RecipientsScreen /></MemoryRouter>);
    expect(await screen.findByText(SCRIPT)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("shows the account masked and the allowlist state", async () => {
    mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [RECIPIENT] }, "/health": { mode: "sandbox" } });
    render(<MemoryRouter><RecipientsScreen /></MemoryRouter>);
    expect(await screen.findByText("GB** **** 4821")).toBeInTheDocument();
    expect(screen.getByText("Not allowlisted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Allowlist with MFA" })).toBeInTheDocument();
  });

  it("explains a malformed BIC before anything is sent", async () => {
    const fetchMock = mockApi({ "/corridors": CORRIDORS, "/recipients": { items: [] }, "/health": { mode: "sandbox" } });
    const { default: userEvent } = await import("@testing-library/user-event");
    render(<MemoryRouter><RecipientsScreen /></MemoryRouter>);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "BAD");
    await userEvent.click(screen.getByRole("button", { name: "Save recipient" }));
    expect(await screen.findByText(/A BIC has 8 or 11 letters and digits/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
  });
});
