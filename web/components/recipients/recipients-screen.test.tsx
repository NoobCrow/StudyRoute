import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/components/providers/auth-provider";
import { RecipientsScreen } from "@/components/recipients/recipients-screen";
import {
  PARENT_PERMISSIONS,
  RECIPIENT,
  STUDENT_PERMISSIONS,
  corridor,
  mockApi,
  user,
} from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const CORRIDORS = { items: [corridor({ account_scheme: "IBAN" })], providers: [] };
const SCRIPT = '<script>window.__pwned = true</script><img src=x onerror="window.__pwned=true">';

function signIn(role: "parent" | "student" = "parent") {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, role === "parent" ? PARENT_PERMISSIONS : STUDENT_PERMISSIONS),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

beforeEach(() => signIn());
afterEach(() => vi.unstubAllGlobals());

describe("recipients screen", () => {
  it("T23: a script tag in a recipient name is shown as plain text and never runs", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [{ ...RECIPIENT, display_name: SCRIPT }] },
      "/health": { mode: "sandbox" },
    });
    const { container } = renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText(SCRIPT)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("shows the account masked and the allowlist state", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [RECIPIENT] },
      "/health": { mode: "sandbox" },
    });
    renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText("GB** **** 4821")).toBeInTheDocument();
    expect(screen.getByText("Not allowlisted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Allowlist with MFA" })).toBeInTheDocument();
  });

  it("explains a malformed BIC before anything is sent", async () => {
    const fetchMock = mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [] },
      "/health": { mode: "sandbox" },
    });
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "BAD");
    await userEvent.click(screen.getByRole("button", { name: "Save recipient" }));
    expect(await screen.findByText(/A BIC has 8 or 11 letters and digits/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST"),
    ).toBe(false);
  });

  it("requires the IBAN where the country uses one", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [] },
      "/health": { mode: "sandbox" },
    });
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "EXMPGB2L");
    await userEvent.click(screen.getByRole("button", { name: "Save recipient" }));
    expect(await screen.findByText("Enter the IBAN.")).toBeInTheDocument();
  });

  it("sends the BIC upper-cased and the IBAN when the form is valid", async () => {
    const fetchMock = mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [] },
      "/health": { mode: "sandbox" },
    });
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "exmpgb2l");
    await userEvent.type(screen.getByLabelText("IBAN"), "GB08EXMP12345612344821");
    await userEvent.click(screen.getByRole("button", { name: "Save recipient" }));
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([, init]) => (init as RequestInit | undefined)?.method === "POST",
        ),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({
      display_name: "Test College",
      bic: "EXMPGB2L",
      iban: "GB08EXMP12345612344821",
    });
  });

  it("gives the student no allowlist button", async () => {
    signIn("student");
    mockApi({
      "/corridors": CORRIDORS,
      "/recipients": { items: [RECIPIENT] },
      "/health": { mode: "sandbox" },
    });
    renderWithProviders(<RecipientsScreen />);
    await screen.findByText("GB** **** 4821");
    expect(screen.queryByRole("button", { name: "Allowlist with MFA" })).toBeNull();
    expect(
      screen.getByText(/Only the paying parent can allowlist a recipient/),
    ).toBeInTheDocument();
  });
});
