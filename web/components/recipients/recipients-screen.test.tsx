import { screen, waitFor, within } from "@testing-library/react";
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
  problem,
  user,
} from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const CORRIDORS = { items: [corridor({ account_scheme: "IBAN" })], providers: [] };
const UK = { items: [corridor({ account_scheme: "IBAN_OR_UK_DOMESTIC" })], providers: [] };
const OTHER = {
  ...RECIPIENT,
  recipient_id: "rcp_2",
  display_name: "FAIL_TEST University (synthetic)",
};
const SCRIPT = '<script>window.__pwned = true</script><img src=x onerror="window.__pwned=true">';
const SANDBOX = { mode: "sandbox", demo: { accounts: [], password: "", mfa_code: "246810" } };
const GOOD_IBAN = "GB08EXMP12345612344821";

function signIn(role: "parent" | "student" = "parent") {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, role === "parent" ? PARENT_PERMISSIONS : STUDENT_PERMISSIONS),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

function routes(recipients: unknown[], extra: Record<string, unknown> = {}, corridors = CORRIDORS) {
  return {
    "/corridors": corridors,
    "/recipients": { items: recipients },
    "/health": SANDBOX,
    ...extra,
  };
}

const methods = (fetchMock: ReturnType<typeof mockApi>, method: string) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === method);

const save = () => screen.getByRole("button", { name: "Save recipient" });

async function fillValid(name = "Test College") {
  await userEvent.type(await screen.findByLabelText("Name"), name);
  await userEvent.type(screen.getByLabelText(/Bank BIC/), "exmpgb2l");
  await userEvent.type(screen.getByLabelText("IBAN"), GOOD_IBAN);
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("recipients list", () => {
  it("T23: a script tag in a recipient name is shown as plain text and never runs", async () => {
    mockApi(routes([{ ...RECIPIENT, display_name: SCRIPT }]));
    const { container } = renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText(SCRIPT)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("shows the counts, the masked account and the allowlist state as the design has them", async () => {
    mockApi(routes([RECIPIENT, OTHER]));
    renderWithProviders(<RecipientsScreen />);
    expect(await screen.findAllByText("GB** **** 4821")).toHaveLength(2);
    expect(screen.getByText("2 recipients")).toBeInTheDocument();
    expect(screen.getByText("0 allowlisted")).toBeInTheDocument();
    expect(screen.getAllByText("Not allowlisted")).toHaveLength(2);
    expect(screen.getAllByText(/University - added 14 Oct 2026/)).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Allowlist with MFA" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Add recipient" })).toBeInTheDocument();
    expect(screen.getByText("Synthetic data only")).toBeInTheDocument();
  });

  it("counts a single recipient in the singular", async () => {
    mockApi(routes([{ ...RECIPIENT, allowlisted: true }]));
    renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText("1 recipient")).toBeInTheDocument();
    expect(screen.getByText("1 allowlisted")).toBeInTheDocument();
  });

  it("shows the empty state, and its button takes the person to the form", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText("No recipients yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add a recipient" }));
    expect(screen.getByRole("combobox", { name: "Type" })).toHaveFocus();
  });

  it("shows a busy status while the list loads", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    expect(screen.getByRole("status", { name: "Loading recipients" })).toBeInTheDocument();
    await screen.findByText("No recipients yet.");
  });

  it("shows the problem and a Retry when the list cannot be loaded", async () => {
    mockApi(
      routes([], { "/recipients": problem(500, "SERVER_ERROR", "The list is unavailable.") }),
    );
    renderWithProviders(<RecipientsScreen />);
    expect(await screen.findByText("The list is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("opens at the form when the address ends in #add", async () => {
    window.history.replaceState(null, "", "/recipients/#add");
    mockApi(routes([RECIPIENT]));
    renderWithProviders(<RecipientsScreen />);
    await screen.findByText("GB** **** 4821");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Type" })).toHaveFocus());
  });

  it("gives the student no allowlist button", async () => {
    signIn("student");
    mockApi(routes([RECIPIENT]));
    renderWithProviders(<RecipientsScreen />);
    await screen.findByText("GB** **** 4821");
    expect(screen.queryByRole("button", { name: "Allowlist with MFA" })).toBeNull();
    expect(
      screen.getByText(/Only the paying parent can allowlist a recipient/),
    ).toBeInTheDocument();
  });
});

describe("allowlist with MFA", () => {
  function allowlistApi(initial: boolean) {
    let allowlisted = initial;
    return mockApi(
      routes([], {
        "/recipients": () => ({ items: [{ ...RECIPIENT, allowlisted }] }),
        "/recipients/rcp_1": (init: RequestInit | undefined) => {
          allowlisted = (JSON.parse(String(init?.body)) as { allowlisted: boolean }).allowlisted;
          return { ...RECIPIENT, allowlisted };
        },
        "/auth/mfa/verify": { mfa_proof: "proof_1" },
      }),
    );
  }

  it("asks for the six-digit code first, then allowlists with the proof, and the badge changes in place", async () => {
    const fetchMock = allowlistApi(false);
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Allowlist with MFA" }));
    const dialog = await screen.findByRole("dialog", { name: "Allowlist this recipient" });
    expect(methods(fetchMock, "PATCH")).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText("MFA code"), "246810");
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Allowlisted")).toBeInTheDocument();
    expect(screen.queryByText("Not allowlisted")).toBeNull();
    expect(screen.getByText("1 allowlisted")).toBeInTheDocument();
    const patchCall = methods(fetchMock, "PATCH")[0];
    expect(JSON.parse(String((patchCall?.[1] as RequestInit).body))).toEqual({
      allowlisted: true,
    });
    expect((patchCall?.[1] as RequestInit).headers).toMatchObject({ "X-MFA-Proof": "proof_1" });
    const verify = methods(fetchMock, "POST").find(([url]) =>
      String(url).endsWith("/auth/mfa/verify"),
    );
    expect(JSON.parse(String((verify?.[1] as RequestInit).body))).toMatchObject({
      scope: "allowlist_recipient",
      subject_id: "rcp_1",
    });
  });

  it("does not allowlist when the code is wrong", async () => {
    const fetchMock = mockApi(
      routes([RECIPIENT], {
        "/auth/mfa/verify": problem(401, "MFA_INVALID", "That code is not valid."),
      }),
    );
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Allowlist with MFA" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("MFA code"), "000000");
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(await within(dialog).findByText("That code is not valid.")).toBeInTheDocument();
    expect(methods(fetchMock, "PATCH")).toHaveLength(0);
    expect(screen.getByText("Not allowlisted")).toBeInTheDocument();
  });

  it("gives focus back to the Allowlist button when the dialog is cancelled", async () => {
    mockApi(routes([RECIPIENT]));
    renderWithProviders(<RecipientsScreen />);
    const button = await screen.findByRole("button", { name: "Allowlist with MFA" });
    await userEvent.click(button);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("removes a recipient from the allowlist only after a confirmation and an MFA code", async () => {
    const fetchMock = allowlistApi(true);
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(
      await screen.findByRole("button", {
        name: /Remove University of Example .* from the allowlist/,
      }),
    );
    const confirm = await screen.findByRole("alertdialog", { name: "Remove from the allowlist?" });
    expect(methods(fetchMock, "PATCH")).toHaveLength(0);
    await userEvent.click(within(confirm).getByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove from the allowlist" });
    await userEvent.type(within(dialog).getByLabelText("MFA code"), "246810");
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Not allowlisted")).toBeInTheDocument();
    const patchCall = methods(fetchMock, "PATCH")[0];
    expect(JSON.parse(String((patchCall?.[1] as RequestInit).body))).toEqual({
      allowlisted: false,
    });
  });

  it("lets the person keep the recipient allowlisted", async () => {
    const fetchMock = allowlistApi(true);
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Remove University of Example/ }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(methods(fetchMock, "PATCH")).toHaveLength(0);
    expect(screen.getByText("Allowlisted")).toBeInTheDocument();
  });
});

describe("add a recipient", () => {
  it("keeps Save disabled until every field is valid", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    await screen.findByLabelText("Name");
    expect(save()).toBeDisabled();
    await fillValid();
    await waitFor(() => expect(save()).toBeEnabled());
  });

  it("explains a malformed BIC after the first blur, before anything is sent", async () => {
    const fetchMock = mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "BAD");
    await userEvent.tab();
    expect(await screen.findByText("A BIC has 8 or 11 characters.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Bank BIC/)).toHaveAttribute("aria-invalid", "true");
    expect(save()).toBeDisabled();
    expect(methods(fetchMock, "POST")).toHaveLength(0);
  });

  it("says the country letters of the BIC must match the country", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText(/Bank BIC/), "EXMPIE2L");
    await userEvent.tab();
    expect(
      await screen.findByText("The country letters in the BIC must match the country."),
    ).toBeInTheDocument();
  });

  it("shows the neutral BIC help, and capitals as the person types", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    const bic = await screen.findByLabelText(/Bank BIC/);
    expect(
      screen.getByText("8 or 11 characters. The country letters must match."),
    ).toBeInTheDocument();
    await userEvent.type(bic, "exmpgb2l");
    expect(bic).toHaveValue("EXMPGB2L");
  });

  it("requires the IBAN, and checks its digits as the person types", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    const field = await screen.findByLabelText("IBAN");
    await userEvent.click(field);
    await userEvent.tab();
    expect(await screen.findByText("Enter the IBAN.")).toBeInTheDocument();

    await userEvent.type(field, "GB09EXMP12345612344821");
    expect(await screen.findByText(/The check digits do not match/)).toBeInTheDocument();
    expect(screen.queryByText(/The check digits are verified/)).toBeNull();

    await userEvent.clear(field);
    await userEvent.type(field, GOOD_IBAN);
    expect(
      await screen.findByText("The check digits are verified (ISO 13616, mod 97)."),
    ).toBeInTheDocument();
  });

  it("fills a synthetic example that is valid as it is", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Fill a synthetic example" }));
    expect(screen.getByLabelText("Name")).toHaveValue("University of Example (synthetic)");
    expect(screen.getByLabelText(/Bank BIC/)).toHaveValue("EXMPGB2L");
    expect(screen.getByLabelText("IBAN")).toHaveValue(GOOD_IBAN);
    await waitFor(() => expect(save()).toBeEnabled());
  });

  it("sends the BIC upper-cased and the IBAN without spaces, then confirms and reloads the list", async () => {
    let list: unknown[] = [];
    const fetchMock = mockApi(
      routes([], {
        "/recipients": (init: RequestInit | undefined) => {
          if (init?.method === "POST") {
            list = [RECIPIENT];
            return RECIPIENT;
          }
          return { items: list };
        },
      }),
    );
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "exmpgb2l");
    await userEvent.type(screen.getByLabelText("IBAN"), "gb08 exmp 1234 5612 3448 21");
    await waitFor(() => expect(save()).toBeEnabled());
    await userEvent.click(save());

    await waitFor(() => expect(methods(fetchMock, "POST")).toHaveLength(1));
    const body = JSON.parse(String((methods(fetchMock, "POST")[0]?.[1] as RequestInit).body));
    expect(body).toMatchObject({ display_name: "Test College", bic: "EXMPGB2L", iban: GOOD_IBAN });
    expect(
      await screen.findByText("Test College was saved. It is not allowlisted yet."),
    ).toBeInTheDocument();
    expect(await screen.findByText("GB** **** 4821")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("IBAN")).toHaveValue("");
  });

  it("shows the server's reason and keeps what was typed when saving fails", async () => {
    mockApi(
      routes([], {
        "/recipients": (init: RequestInit | undefined) =>
          init?.method === "POST"
            ? problem(422, "VALIDATION_ERROR", "That IBAN is not accepted.")
            : { items: [] },
      }),
    );
    renderWithProviders(<RecipientsScreen />);
    await fillValid();
    await waitFor(() => expect(save()).toBeEnabled());
    await userEvent.click(save());
    expect(await screen.findByText("That IBAN is not accepted.")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Test College");
  });

  it("never writes an account number to storage or the address", async () => {
    mockApi(routes([]));
    renderWithProviders(<RecipientsScreen />);
    await fillValid();
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(GOOD_IBAN);
    expect(window.location.href).not.toContain("GB08");
    expect(screen.getByLabelText("IBAN")).toHaveAttribute("autocomplete", "off");
  });
});

describe("account format", () => {
  it("offers IBAN or UK sort code and account as cards for the United Kingdom", async () => {
    mockApi(routes([], {}, UK));
    renderWithProviders(<RecipientsScreen />);
    const group = await screen.findByRole("radiogroup", { name: "Account format" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[0]).toBeChecked();
    expect(
      within(group).getByText("One number that holds the bank and the account."),
    ).toBeInTheDocument();
    expect(
      within(group).getByText("A 6-digit sort code and an 8-digit account number."),
    ).toBeInTheDocument();
  });

  it("switches to the sort code and account number fields, and checks them", async () => {
    mockApi(routes([], {}, UK));
    renderWithProviders(<RecipientsScreen />);
    await userEvent.click(await screen.findByRole("radio", { name: /UK sort code and account/ }));
    expect(screen.queryByLabelText("IBAN")).toBeNull();
    const sort = screen.getByLabelText("Sort code");
    const account = screen.getByLabelText("Account number");
    expect(sort).toHaveAttribute("inputmode", "numeric");
    await userEvent.type(sort, "12-34");
    await userEvent.type(account, "1234");
    await userEvent.tab();
    expect(await screen.findByText("A sort code has 6 digits.")).toBeInTheDocument();
    expect(screen.getByText("A UK account number has 8 digits.")).toBeInTheDocument();
  });

  it("sends the sort code as the routing code, digits only", async () => {
    const fetchMock = mockApi(routes([], { "/recipients": () => ({ items: [] }) }, UK));
    renderWithProviders(<RecipientsScreen />);
    await userEvent.type(await screen.findByLabelText("Name"), "Test College");
    await userEvent.type(screen.getByLabelText(/Bank BIC/), "EXMPGB2L");
    await userEvent.click(screen.getByRole("radio", { name: /UK sort code and account/ }));
    await userEvent.type(screen.getByLabelText("Sort code"), "12-34-56");
    await userEvent.type(screen.getByLabelText("Account number"), "12345678");
    await waitFor(() => expect(save()).toBeEnabled());
    await userEvent.click(save());
    await waitFor(() => expect(methods(fetchMock, "POST")).toHaveLength(1));
    expect(
      JSON.parse(String((methods(fetchMock, "POST")[0]?.[1] as RequestInit).body)),
    ).toMatchObject({
      account_number: "12345678",
      routing_code: "123456",
    });
  });
});
