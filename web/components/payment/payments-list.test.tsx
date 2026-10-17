import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PaymentsScreen } from "@/components/payment/payments-screen";
import { useAuth } from "@/components/providers/auth-provider";
import type { PaymentBrief } from "@/lib/api/types";
import { PARENT_PERMISSIONS, STUDENT_PERMISSIONS, mockApi, problem, user } from "@/tests/fixtures";
import { setLocation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const NOW = new Date("2026-10-16T08:00:00Z");

function pay(id: string, over: Partial<PaymentBrief> = {}): PaymentBrief {
  return {
    payment_id: `pay_${id}`,
    state: "QUOTED",
    target: { amount_minor: 1000000, currency: "GBP", formatted: "GBP 10,000.00" },
    provider_id: "prov_b",
    provider_name: "Provider B (synthetic)",
    recipient_label: "University of Example (synthetic) GB** **** 4821",
    reference: `INV-${id}`,
    due_date: "2026-10-30",
    uetr: null,
    parent_pays: "BDT 1,625,300.00",
    created_at: "2026-10-14T09:31:00Z",
    updated_at: "2026-10-14T09:31:00Z",
    ...over,
  };
}

const SAMPLE = [
  pay("1", { state: "QUOTED" }),
  pay("2", {
    state: "SETTLED",
    reference: "FEES-2026",
    recipient_label: "Maple Street Student (synthetic) GB** **** 1111",
    created_at: "2026-10-12T09:00:00Z",
  }),
  pay("3", {
    state: "FAILED",
    target: { amount_minor: 150000000, currency: "JPY", formatted: "JPY 1,500,000" },
    created_at: "2026-10-13T09:00:00Z",
  }),
  pay("4", { state: "SUBMITTED", created_at: "2026-10-11T09:00:00Z" }),
  pay("5", { state: "CANCELLED", created_at: "2026-10-10T09:00:00Z" }),
  pay("6", { state: "PENDING_APPROVAL", created_at: "2026-08-01T09:00:00Z" }),
];

function signIn(role: "parent" | "student" = "parent") {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, role === "parent" ? PARENT_PERMISSIONS : STUDENT_PERMISSIONS),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

function list(items: PaymentBrief[]) {
  return { items, next_cursor: null };
}

/** The list has loaded once the count line shows a number. */
const ready = () => screen.findByText(/^\d+ payments?$/);
const rows = () =>
  within(screen.getByRole("region", { name: "Payments table" }))
    .getAllByRole("row")
    .slice(1);
const refs = () => rows().map((r) => within(r).getAllByRole("cell")[0]?.textContent);

beforeEach(() => {
  signIn();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("payments list: states", () => {
  it("shows the empty state with the design's words, zero counts and a disabled Export", async () => {
    mockApi({ "/payments": list([]) });
    renderWithProviders(<PaymentsScreen />);
    expect(await screen.findByText("No payments yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compare providers to start one." })).toHaveAttribute(
      "href",
      "/compare/",
    );
    expect(screen.getByRole("link", { name: "New comparison" })).toHaveAttribute(
      "href",
      "/compare/",
    );
    expect(screen.getByText("0 payments")).toBeInTheDocument();
    for (const name of ["All", "In progress", "Completed", "Needs attention"]) {
      expect(screen.getByRole("tab", { name: new RegExp(`^${name}\\s*0$`) })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Export" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next page/i })).toBeDisabled();
  });

  it("explains the three steps in a Simulated card", async () => {
    mockApi({ "/payments": list([]) });
    renderWithProviders(<PaymentsScreen />);
    const card = await screen.findByRole("region", { name: "How a payment works here" });
    expect(within(card).getByText("Simulated")).toBeInTheDocument();
    const steps = within(card).getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Compare");
    expect(steps[1]).toHaveTextContent("Check");
    expect(steps[2]).toHaveTextContent("Simulated only. Nothing reaches a real bank.");
  });

  it("shows a busy status while the list loads", async () => {
    mockApi({ "/payments": list([]) });
    renderWithProviders(<PaymentsScreen />);
    expect(
      screen
        .getAllByRole("status")
        .some((el) =>
          /Loading payments/.test(el.textContent ?? el.getAttribute("aria-label") ?? ""),
        ),
    ).toBe(true);
    await screen.findByText("No payments yet.");
  });

  it("shows the problem and a Retry when the list cannot be loaded", async () => {
    mockApi({ "/payments": problem(500, "SERVER_ERROR", "The list is unavailable.") });
    renderWithProviders(<PaymentsScreen />);
    expect(await screen.findByText("The list is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows a different empty state, with Clear filters, when nothing matches", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.type(screen.getByLabelText("Search by reference or recipient"), "zzz-nothing");
    expect(await screen.findByText("No payments match these filters.")).toBeInTheDocument();
    expect(screen.queryByText("No payments yet.")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByRole("region", { name: "Payments table" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search by reference or recipient")).toHaveValue("");
    expect(screen.getByText("6 payments")).toBeInTheDocument();
  });
});

describe("payments list: rows and counts", () => {
  it("shows each payment as the design has it, with amounts exactly as the API formatted them", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    const first = rows().find((r) => within(r).queryByText("INV-1")) as HTMLElement;
    expect(
      within(first).getByText("University of Example (synthetic) GB** **** 4821"),
    ).toBeInTheDocument();
    expect(within(first).getByText("GBP 10,000.00")).toBeInTheDocument();
    expect(within(first).getByText("Provider B (synthetic)")).toBeInTheDocument();
    expect(within(first).getByText("In progress")).toBeInTheDocument();
    expect(within(first).getByText("2 days ago")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent?.trim())).toEqual([
      "Reference",
      "Recipient",
      "Beneficiary receives",
      "Provider",
      "Status",
      "Created",
      "Actions",
    ]);
  });

  it("uses the default Last 30 days, so a payment from August is not listed", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    expect(refs()).not.toContain("INV-6");
    expect(screen.getByText("5 payments")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Last 30 days/ })).toBeInTheDocument();
  });

  it("counts the tabs from the list, with a cancelled payment only under All", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    expect(screen.getByRole("tab", { name: /^All\s*5$/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^In progress\s*2$/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Completed\s*1$/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Needs attention\s*1$/ })).toBeInTheDocument();
  });

  it("switches tabs, keeps the count words and writes the status into the address", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("tab", { name: /^Completed/ }));
    expect(refs()).toEqual(["FEES-2026"]);
    expect(screen.getByText("1 payment")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Completed/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() => expect(window.location.search).toBe("?status=completed"));
    await userEvent.click(screen.getByRole("tab", { name: /^Needs attention/ }));
    expect(refs()).toEqual(["INV-3"]);
  });

  it("opens a shared view from the address", async () => {
    setLocation("/payments/", "status=completed&range=all");
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    expect(screen.getByRole("tab", { name: /^Completed/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("button", { name: /All time/ })).toBeInTheDocument();
  });

  it("searches reference and recipient after a short pause", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    const box = screen.getByLabelText("Search by reference or recipient");
    await userEvent.type(box, "maple");
    await waitFor(() => expect(refs()).toEqual(["FEES-2026"]));
    await waitFor(() => expect(window.location.search).toBe("?q=maple"));
    await userEvent.clear(box);
    await userEvent.type(box, "inv-4");
    await waitFor(() => expect(refs()).toEqual(["INV-4"]));
  });

  it("includes older payments when the range is All time", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: /Last 30 days/ }));
    await userEvent.click(await screen.findByRole("button", { name: "All time" }));
    await waitFor(() => expect(refs()).toContain("INV-6"));
    expect(screen.getByText("6 payments")).toBeInTheDocument();
  });

  it("narrows to the last 7 days", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: /Last 30 days/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Last 7 days" }));
    // 7 days ending 16 Oct start on 10 Oct: INV-5 (10 Oct, Dhaka) is in, August is out.
    await waitFor(() => expect(refs()).not.toContain("INV-6"));
    expect(refs()).toContain("INV-5");
  });

  it("filters by currency from the codes that are in the list", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("combobox", { name: "Currency" }));
    await userEvent.click(await screen.findByRole("option", { name: "JPY" }));
    await waitFor(() => expect(refs()).toEqual(["INV-3"]));
    expect(screen.getByText("JPY 1,500,000")).toBeInTheDocument();
  });
});

describe("payments list: sorting and pages", () => {
  it("sorts by a column, says so with aria-sort, and reverses on a second press", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    const created = screen.getByRole("columnheader", { name: /Created/ });
    expect(created).toHaveAttribute("aria-sort", "descending");
    expect(refs()[0]).toBe("INV-1");

    await userEvent.click(
      within(screen.getByRole("columnheader", { name: /Reference/ })).getByRole("button"),
    );
    expect(screen.getByRole("columnheader", { name: /Reference/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    expect(refs()).toEqual(["FEES-2026", "INV-1", "INV-3", "INV-4", "INV-5"]);
    await userEvent.click(
      within(screen.getByRole("columnheader", { name: /Reference/ })).getByRole("button"),
    );
    expect(refs()[0]).toBe("INV-5");
    expect(created).toHaveAttribute("aria-sort", "none");
  });

  it("pages through a long list ten at a time, and writes the page into the address", async () => {
    const many = Array.from({ length: 23 }, (_, i) =>
      pay(String(i + 100), {
        created_at: `2026-10-${String(15 - Math.floor(i / 3)).padStart(2, "0")}T09:00:00Z`,
        reference: `REF-${String(i + 100)}`,
      }),
    );
    mockApi({ "/payments": list(many) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    expect(rows()).toHaveLength(10);
    expect(screen.getByText("23 payments")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /next page/i }));
    expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(window.location.search).toBe("?page=2"));
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    expect(rows()).toHaveLength(3);
    expect(screen.getByRole("button", { name: /next page/i })).toBeDisabled();
  });
});

describe("payments list: opening one", () => {
  it("opens the detail sheet from a click and from Enter, and links to the full page", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    const row = rows().find((r) => within(r).queryByText("INV-1")) as HTMLElement;
    await userEvent.click(row);
    const sheet = await screen.findByRole("dialog", { name: "INV-1" });
    expect(
      within(sheet).getByText("Simulated. Nothing was sent to a real bank."),
    ).toBeInTheDocument();
    expect(within(sheet).getByText("GBP 10,000.00")).toBeInTheDocument();
    expect(within(sheet).getByText("BDT 1,625,300.00")).toBeInTheDocument();
    expect(within(sheet).getByRole("link", { name: "Open the full page" })).toHaveAttribute(
      "href",
      "/payments/view/?id=pay_1",
    );
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const again = rows().find((r) => within(r).queryByText("FEES-2026")) as HTMLElement;
    again.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "FEES-2026" })).toBeInTheDocument();
  });

  it("makes every row reachable with the keyboard", async () => {
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    for (const row of rows()) expect(row).toHaveAttribute("tabindex", "0");
  });

  it("shows a recipient name with markup as plain text", async () => {
    const evil = '<img src=x onerror="window.__pwned=1">';
    mockApi({ "/payments": list([pay("1", { recipient_label: evil })]) });
    const { container } = renderWithProviders(<PaymentsScreen />);
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("cancelling a payment", () => {
  function cancelApi() {
    let cancelled = false;
    const fetchMock = mockApi({
      "/payments": () =>
        list(cancelled ? [pay("1", { state: "CANCELLED" })] : [pay("1", { state: "QUOTED" })]),
      "/payments/pay_1/cancel": () => {
        cancelled = true;
        return { payment_id: "pay_1", state: "CANCELLED" };
      },
    });
    return fetchMock;
  }

  it("asks first, cancels with an Idempotency-Key, and the counts update", async () => {
    const fetchMock = cancelApi();
    renderWithProviders(<PaymentsScreen />);
    await ready();
    expect(screen.getByRole("tab", { name: /^In progress\s*1$/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Actions for INV-1" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Cancel payment" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel this payment?" });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/cancel"))).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel payment" }));

    expect(await screen.findByRole("tab", { name: /^In progress\s*0$/ })).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/cancel"));
    const headers = (call?.[1] as RequestInit).headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect((call?.[1] as RequestInit).method).toBe("POST");
  });

  it("lets the person keep the payment", async () => {
    const fetchMock = cancelApi();
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Actions for INV-1" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Cancel payment" }));
    await userEvent.click(await screen.findByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/cancel"))).toBe(false);
  });

  it("shows the server's reason inside the dialog when the payment cannot be cancelled", async () => {
    mockApi({
      "/payments": list([pay("1")]),
      "/payments/pay_1/cancel": problem(
        409,
        "INVALID_STATE",
        "This payment can no longer be cancelled.",
      ),
    });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Actions for INV-1" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Cancel payment" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Cancel payment",
      }),
    );
    expect(await screen.findByText("This payment can no longer be cancelled.")).toBeInTheDocument();
  });

  it("offers Cancel only where the server allows it", async () => {
    mockApi({
      "/payments": list([pay("4", { state: "SUBMITTED" }), pay("2", { state: "SETTLED" })]),
    });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    for (const name of ["Actions for INV-4", "Actions for INV-2"]) {
      await userEvent.click(screen.getByRole("button", { name }));
      expect(await screen.findByRole("menuitem", { name: "View details" })).toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: "Cancel payment" })).toBeNull();
      await userEvent.keyboard("{Escape}");
    }
  });

  it("gives the student no way to cancel", async () => {
    signIn("student");
    mockApi({ "/payments": list([pay("1")]) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("button", { name: "Actions for INV-1" }));
    expect(await screen.findByRole("menuitem", { name: "View details" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Cancel payment" })).toBeNull();
  });
});

describe("export", () => {
  it("downloads the rows on screen as CSV, nothing more", async () => {
    let blob: Blob | null = null;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: (b: Blob) => {
        blob = b;
        return "blob:test";
      },
      revokeObjectURL: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    mockApi({ "/payments": list(SAMPLE) });
    renderWithProviders(<PaymentsScreen />);
    await ready();
    await userEvent.click(screen.getByRole("tab", { name: /^Completed/ }));
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(click).toHaveBeenCalledTimes(1);
    const csv = await (blob as unknown as Blob).text();
    expect(csv.split("\r\n")[0]).toBe(
      "Reference,Recipient,Beneficiary receives,Provider,Status,Created",
    );
    expect(csv).toContain("FEES-2026");
    expect(csv).not.toContain("INV-1");
    click.mockRestore();
  });

  it("says why Export is off when there is nothing to export", async () => {
    mockApi({ "/payments": list([]) });
    renderWithProviders(<PaymentsScreen />);
    await screen.findByText("No payments yet.");
    await userEvent.hover(
      screen.getByRole("button", { name: "Export" }).parentElement as HTMLElement,
    );
    expect((await screen.findAllByText("Nothing to export yet"))[0]).toBeInTheDocument();
  });
});
