import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DraftForm } from "@/components/compare/draft-form";
import { QUOTE, RECIPIENT, mockApi, payment, problem } from "@/tests/fixtures";
import { navigation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

const ALLOWED = { ...RECIPIENT, allowlisted: true };
const OTHER = {
  ...RECIPIENT,
  recipient_id: "rcp_2",
  display_name: "FAIL_TEST University (synthetic)",
};

/** The same form instance, so a re-render with other recipients behaves like a list that loaded late. */
function LateForm({ recipients }: { recipients: (typeof ALLOWED)[] }) {
  return (
    <DraftForm quote={QUOTE} providerId="prov_b" recipients={recipients} initialRecipient="" />
  );
}

function renderForm(recipients = [ALLOWED]) {
  return renderWithProviders(
    <DraftForm quote={QUOTE} providerId="prov_b" recipients={recipients} initialRecipient="" />,
  );
}

async function fillReference(text = "INV-1 / STU-9") {
  await userEvent.type(screen.getByLabelText("Payment reference"), text);
}

const posts = (fetchMock: ReturnType<typeof mockApi>, path: string) =>
  fetchMock.mock.calls.filter(
    ([url, init]) =>
      String(url).endsWith(path) && (init as RequestInit | undefined)?.method === "POST",
  );
const keyOf = (call: unknown[]) =>
  (call[1] as { headers: Record<string, string> }).headers["Idempotency-Key"];

afterEach(() => vi.unstubAllGlobals());

describe("the draft form: choosing who gets the money", () => {
  it("preselects the one recipient that can be paid when the others are not allowlisted yet", () => {
    mockApi({});
    renderForm([OTHER, ALLOWED]);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      ALLOWED.display_name,
    );
  });

  it("chooses it when the recipients arrive after the form is first shown", async () => {
    mockApi({});
    const view = render(<LateForm recipients={[]} />);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      "Choose a recipient",
    );
    view.rerender(<LateForm recipients={[OTHER, ALLOWED]} />);
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
        ALLOWED.display_name,
      ),
    );
  });

  it("never replaces a recipient the person chose themselves", async () => {
    mockApi({});
    const view = render(<LateForm recipients={[OTHER, RECIPIENT]} />);
    await userEvent.click(screen.getByRole("combobox", { name: "Recipient" }));
    await userEvent.click(await screen.findByRole("option", { name: /FAIL_TEST University/ }));
    view.rerender(<LateForm recipients={[OTHER, ALLOWED]} />);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      OTHER.display_name,
    );
  });

  it("does not guess when two recipients can be paid", () => {
    mockApi({});
    renderForm([{ ...OTHER, allowlisted: true }, ALLOWED]);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      "Choose a recipient",
    );
  });

  it("does not guess when two exist and none is allowlisted", () => {
    mockApi({});
    renderForm([OTHER, RECIPIENT]);
    expect(screen.getByRole("combobox", { name: "Recipient" })).toHaveTextContent(
      "Choose a recipient",
    );
  });
});

describe("the draft form: fewer clicks to a payment waiting for approval", () => {
  it("offers both ways, and keeps them off until there is a reference", async () => {
    mockApi({});
    renderForm();
    const quick = screen.getByRole("button", { name: "Create draft and request approval" });
    const plain = screen.getByRole("button", { name: "Create draft with Provider B (synthetic)" });
    expect(quick).toBeDisabled();
    expect(plain).toBeDisabled();
    await fillReference();
    expect(quick).toBeEnabled();
    expect(plain).toBeEnabled();
  });

  it("keeps them off while no recipient is chosen", async () => {
    mockApi({});
    renderForm([OTHER, RECIPIENT]);
    await fillReference();
    expect(
      screen.getByRole("button", { name: "Create draft and request approval" }),
    ).toBeDisabled();
  });

  it("creates the draft and asks for approval in one click, then opens the payment", async () => {
    const fetchMock = mockApi({
      "/payments": payment(),
      "/payments/pay_1/request-approval": { payment_id: "pay_1", state: "PENDING_APPROVAL" },
    });
    renderForm();
    await fillReference();
    await userEvent.click(
      screen.getByRole("button", { name: "Create draft and request approval" }),
    );
    await waitFor(() =>
      expect(navigation.router.push).toHaveBeenCalledWith("/payments/view/?id=pay_1"),
    );
    expect(posts(fetchMock, "/payments")).toHaveLength(1);
    expect(posts(fetchMock, "/payments/pay_1/request-approval")).toHaveLength(1);
    // Approving is not part of it: nothing was sent to approve, and no MFA proof was used.
    expect(posts(fetchMock, "/payments/pay_1/approve")).toHaveLength(0);
    const draft = JSON.parse(
      String((posts(fetchMock, "/payments")[0]?.[1] as RequestInit).body),
    ) as Record<string, unknown>;
    expect(draft).toMatchObject({ recipient_id: "rcp_1", reference: "INV-1 / STU-9" });
  });

  it("sends an Idempotency-Key with both calls", async () => {
    const fetchMock = mockApi({
      "/payments": payment(),
      "/payments/pay_1/request-approval": { payment_id: "pay_1", state: "PENDING_APPROVAL" },
    });
    renderForm();
    await fillReference();
    await userEvent.click(
      screen.getByRole("button", { name: "Create draft and request approval" }),
    );
    await waitFor(() => expect(navigation.router.push).toHaveBeenCalled());
    const draftKey = keyOf(posts(fetchMock, "/payments")[0] ?? []);
    const approvalKey = keyOf(posts(fetchMock, "/payments/pay_1/request-approval")[0] ?? []);
    expect(draftKey).toBeTruthy();
    expect(approvalKey).toBeTruthy();
    expect(approvalKey).not.toBe(draftKey);
  });

  it("only creates the draft, and says why, when approval cannot be requested yet", async () => {
    const blocked = payment({
      readiness: {
        blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC is not verified (simulated)." }],
        can_request_approval: false,
        can_approve: false,
      },
    });
    const fetchMock = mockApi({ "/payments": blocked });
    renderForm();
    await fillReference();
    await userEvent.click(
      screen.getByRole("button", { name: "Create draft and request approval" }),
    );
    await waitFor(() =>
      expect(navigation.router.push).toHaveBeenCalledWith("/payments/view/?id=pay_1"),
    );
    expect(posts(fetchMock, "/payments/pay_1/request-approval")).toHaveLength(0);
  });

  it("the plain button still only creates the draft", async () => {
    const fetchMock = mockApi({ "/payments": payment() });
    renderForm();
    await fillReference();
    await userEvent.click(
      screen.getByRole("button", { name: "Create draft with Provider B (synthetic)" }),
    );
    await waitFor(() => expect(navigation.router.push).toHaveBeenCalled());
    expect(posts(fetchMock, "/payments")).toHaveLength(1);
    expect(posts(fetchMock, "/payments/pay_1/request-approval")).toHaveLength(0);
  });

  it("stays on the page with the reason when approval is refused, and a retry reuses the same keys", async () => {
    let refuse = true;
    const fetchMock = mockApi({
      "/payments": payment(),
      "/payments/pay_1/request-approval": () =>
        refuse
          ? problem(422, "KYC_NOT_VERIFIED", "KYC is not verified (simulated).")
          : { payment_id: "pay_1", state: "PENDING_APPROVAL" },
    });
    renderForm();
    await fillReference();
    const button = screen.getByRole("button", { name: "Create draft and request approval" });
    await userEvent.click(button);
    expect(await screen.findByText("KYC is not verified (simulated).")).toBeInTheDocument();
    expect(navigation.router.push).not.toHaveBeenCalled();
    refuse = false;
    await userEvent.click(button);
    await waitFor(() => expect(navigation.router.push).toHaveBeenCalled());
    const drafts = posts(fetchMock, "/payments");
    expect(drafts).toHaveLength(2);
    expect(keyOf(drafts[0] ?? [])).toBe(keyOf(drafts[1] ?? []));
    const approvals = posts(fetchMock, "/payments/pay_1/request-approval");
    expect(keyOf(approvals[0] ?? [])).toBe(keyOf(approvals[1] ?? []));
  });

  it("keeps both buttons off while it works", async () => {
    let release: (reply: Response) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            release = resolve;
          }),
      ),
    );
    renderForm();
    await fillReference();
    await userEvent.click(
      screen.getByRole("button", { name: "Create draft and request approval" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Create draft with Provider B (synthetic)" }),
      ).toBeDisabled(),
    );
    expect(
      screen.getByRole("button", { name: /Create draft and request approval/ }),
    ).toBeDisabled();
    release(problem(500, "STOPPED", "Stopped for the test."));
    expect(await screen.findByText("Stopped for the test.")).toBeInTheDocument();
  });
});
