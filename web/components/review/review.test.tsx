import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ParentReviewPanel } from "@/components/review/parent-review-panel";
import { ReviewDesk } from "@/components/review/review-desk";
import { ReviewerBriefCard } from "@/components/review/reviewer-brief";
import type { ParentReview, ReviewerBrief } from "@/lib/api/types";
import { mockApi, problem } from "@/tests/fixtures";
import { BRIEF, QUEUE, WAITING } from "@/tests/review";
import { renderWithProviders } from "@/tests/render";

afterEach(() => vi.unstubAllGlobals());

function headersOf(fetchMock: ReturnType<typeof mockApi>, path: string) {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith(path));
  return {
    call,
    headers: (call?.[1] as RequestInit | undefined)?.headers as Record<string, string>,
  };
}

describe("ParentReviewPanel", () => {
  it("says in plain words that the bank is looking, how long is left and what to have ready", async () => {
    mockApi({ "/payments/pay_1/bank-review": WAITING });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    expect(await screen.findByText("Waiting for the bank", { selector: "p" })).toBeInTheDocument();
    expect(
      screen.getByText(/About 23 h 0 min left of the bank's 24-hour target/),
    ).toBeInTheDocument();
    expect(screen.getByText("Large payment")).toBeInTheDocument();
    expect(screen.getByText("The university's invoice")).toBeInTheDocument();
    expect(screen.getByText(/Indicative\. Confirm with your AD bank/)).toBeInTheDocument();
  });

  it("explains the bank's words and never accuses anyone", async () => {
    mockApi({ "/payments/pay_1/bank-review": WAITING });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    await screen.findByText("Large payment");
    expect(screen.getByText("Words the bank uses")).toBeInTheDocument();
    expect(
      screen.getByText(/A bank allowed to handle foreign-currency payments/),
    ).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    for (const word of ["launder", "illegal", "criminal", "fraud"])
      expect(text).not.toContain(word);
  });

  it("shows the AI risk score with its four factors, and a warning when the score is medium or high", async () => {
    mockApi({ "/payments/pay_1/bank-review": WAITING });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    const card = await screen.findByRole("region", { name: "AI risk score" });
    expect(card).toHaveTextContent("AI risk score 97 out of 100");
    expect(card).toHaveTextContent("medium risk");
    expect(within(card).getByRole("status")).toHaveTextContent("Warning");
    expect(card).toHaveTextContent("more unusual than 97% of the practice payments");
    const factors = within(card).getByRole("list", { name: "What the score is made of" });
    const rows = within(factors).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Amount"),
      expect.stringContaining("Frequency"),
      expect.stringContaining("Timeline"),
      expect.stringContaining("Person"),
    ]);
    expect(rows[0]).toHaveTextContent("raises the score");
    expect(rows[1]).toHaveTextContent("no effect");
    expect(rows[2]).toHaveTextContent("lowers the score");
    expect(card).toHaveTextContent("about 3.2% of payments rated like this were flagged");
    expect(card).toHaveTextContent(
      "Every payment needs a person's authorization, whatever its score",
    );
  });

  it("shows no warning when the score is low, and still says authorization is needed", async () => {
    mockApi({
      "/payments/pay_1/bank-review": {
        ...WAITING,
        status: "CLEARED_AUTO",
        headline: "No bank check needed",
        signals: [],
        ai: {
          ...WAITING.ai!,
          score: 12,
          band: "LOW",
          warning: false,
          drivers: [],
          hit_rate: 0.0005,
        },
      } satisfies ParentReview,
    });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    const card = await screen.findByRole("region", { name: "AI risk score" });
    expect(card).toHaveTextContent("AI risk score 12 out of 100");
    expect(card).toHaveTextContent("No warning");
    expect(within(card).queryByRole("status")).not.toBeInTheDocument();
    expect(within(card).queryByRole("alert")).not.toBeInTheDocument();
    expect(card).toHaveTextContent("Every payment needs a person's authorization");
  });

  it("sends a reminder with an Idempotency-Key and no MFA", async () => {
    const fetchMock = mockApi({
      "/payments/pay_1/bank-review": WAITING,
      "/payments/pay_1/bank-review/remind": { ...WAITING, can_remind: false, reminders_sent: 1 },
    });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Remind the bank" }));
    const { call, headers } = headersOf(fetchMock, "/bank-review/remind");
    expect((call?.[1] as RequestInit).method).toBe("POST");
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers["X-MFA-Proof"]).toBeUndefined();
  });

  it("shows the bank's question and sends the parent's answer", async () => {
    const asked: ParentReview = {
      ...WAITING,
      status: "INFO_REQUESTED",
      headline: "The bank has a question",
      reviewer_asked: "Please send the fee demand note.",
      can_reply: true,
      can_remind: false,
      clock: { running: false, state: "not_running", target_hours: 24 },
    };
    const fetchMock = mockApi({
      "/payments/pay_1/bank-review": asked,
      "/payments/pay_1/bank-review/reply": { ...asked, status: "OPEN" },
    });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    expect(await screen.findByText("Please send the fee demand note.")).toBeInTheDocument();
    const send = screen.getByRole("button", { name: "Send my answer" });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your answer to the bank"), "Uploaded it today.");
    await userEvent.click(send);
    const { call } = headersOf(fetchMock, "/bank-review/reply");
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      message: "Uploaded it today.",
    });
  });

  it("shows why the bank said no", async () => {
    mockApi({
      "/payments/pay_1/bank-review": {
        ...WAITING,
        status: "DECLINED",
        headline: "The bank said no",
        decision_reason: "The receiver's name does not match the invoice.",
        decision_note: "Name differs.",
        can_remind: false,
        signals: [],
      } satisfies ParentReview,
    });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    expect(await screen.findByText(/name does not match the invoice/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remind the bank" })).not.toBeInTheDocument();
  });

  it("is quiet in the fast lane: no signals, no buttons", async () => {
    mockApi({
      "/payments/pay_1/bank-review": {
        ...WAITING,
        status: "CLEARED_AUTO",
        headline: "No bank check needed",
        lane: "fast",
        signals: [],
        can_remind: false,
        clock: { running: false, state: "not_running", target_hours: 24 },
      } satisfies ParentReview,
    });
    renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    expect(await screen.findByText("No bank check needed", { selector: "p" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders nothing when there is no review yet", async () => {
    mockApi({ "/payments/pay_1/bank-review": problem(404, "NOT_FOUND", "No review yet") });
    const { container } = renderWithProviders(<ParentReviewPanel paymentId="pay_1" />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ReviewerBriefCard", () => {
  it("puts the facts, the reasons, the hint and the priority on one page", async () => {
    mockApi({ "/payments/pay_1/bank-review": BRIEF });
    renderWithProviders(<ReviewerBriefCard paymentId="pay_1" />);
    expect(await screen.findByText("GBP 32,000.00 for tuition to GB")).toBeInTheDocument();
    expect(screen.getByText(/amount: USD 41,967.00/)).toBeInTheDocument();
    expect(screen.getByText(/A rule-based hint\. The reviewer decides\./)).toBeInTheDocument();
    const chip = screen.getByText(/Risk 97 · medium/);
    expect(chip).toHaveAttribute("title", expect.stringContaining("A person decides"));
  });

  it("shows what drove the AI's score, and says when the model is not loaded", async () => {
    mockApi({ "/payments/pay_1/bank-review": BRIEF });
    const first = renderWithProviders(<ReviewerBriefCard paymentId="pay_1" />);
    expect(await screen.findByRole("region", { name: "AI risk score" })).toBeInTheDocument();
    first.unmount();
    mockApi({ "/payments/pay_1/bank-review": { ...BRIEF, ai: null, routing: "rules" } });
    renderWithProviders(<ReviewerBriefCard paymentId="pay_1" />);
    expect(await screen.findByText("No AI reading")).toBeInTheDocument();
  });

  it("needs a reason and a note to ask or decline, but not to clear", async () => {
    mockApi({ "/payments/pay_1/bank-review": BRIEF });
    renderWithProviders(<ReviewerBriefCard paymentId="pay_1" />);
    const send = await screen.findByRole("button", { name: "Sign with MFA and send" });
    expect(send).toBeDisabled(); // nothing is chosen for the reviewer
    expect(screen.getByLabelText(/Yes, clear it/)).not.toBeChecked();
    await userEvent.click(screen.getByLabelText(/Yes, clear it/));
    expect(send).toBeEnabled();
    await userEvent.click(screen.getByLabelText(/Ask for more/));
    expect(send).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Reason"), "DOCUMENTS_MISSING");
    await userEvent.type(screen.getByLabelText("Note for the parent"), "Please send the invoice.");
    expect(send).toBeEnabled();
  });

  it("signs a decision with a fresh MFA proof for this payment", async () => {
    const fetchMock = mockApi({
      "/payments/pay_1/bank-review": BRIEF,
      "/auth/mfa/verify": { mfa_proof: "proof_1" },
      "/payments/pay_1/bank-review/decision": { ...BRIEF, status: "CLEARED", can_decide: false },
    });
    renderWithProviders(<ReviewerBriefCard paymentId="pay_1" sandboxCode="246810" />);
    await userEvent.click(await screen.findByLabelText(/Yes, clear it/));
    await userEvent.click(screen.getByRole("button", { name: "Sign with MFA and send" }));
    const dialog = await screen.findByRole("dialog", { name: "Sign this decision" });
    await userEvent.type(within(dialog).getByLabelText("MFA code"), "246810");
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await vi.waitFor(() =>
      expect(headersOf(fetchMock, "/bank-review/decision").call).toBeDefined(),
    );
    const verify = headersOf(fetchMock, "/auth/mfa/verify").call;
    expect(JSON.parse(String((verify?.[1] as RequestInit).body))).toMatchObject({
      scope: "review_payment",
      subject_id: "pay_1",
    });
    const { call, headers } = headersOf(fetchMock, "/bank-review/decision");
    expect(headers["X-MFA-Proof"]).toBe("proof_1");
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({
      decision: "CLEAR",
    });
  });

  it("offers no buttons once the decision is made", async () => {
    mockApi({
      "/payments/pay_1/bank-review": {
        ...BRIEF,
        status: "CLEARED",
        can_decide: false,
        decided_at: "2026-10-18T10:00:00Z",
      } satisfies ReviewerBrief,
    });
    renderWithProviders(<ReviewerBriefCard paymentId="pay_1" />);
    await screen.findByText(/Decided 2026-10-18T10:00:00Z/);
    expect(
      screen.queryByRole("button", { name: "Sign with MFA and send" }),
    ).not.toBeInTheDocument();
  });
});

describe("ReviewDesk", () => {
  it("lists what waits, the most overdue first, with the clock, the reminder and the priority", async () => {
    mockApi({ "/bank-review/queue": QUEUE });
    renderWithProviders(<ReviewDesk />);
    expect(await screen.findByText("Large payment, No invoice on file")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("reminded")).toBeInTheDocument();
    expect(screen.getByText(/Risk 99 · high/)).toBeInTheDocument();
    expect(screen.getByText("5.5 h")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open brief" })).toHaveAttribute(
      "href",
      "/payments/view/?id=pay_9",
    );
  });

  it("says plainly when nothing waits", async () => {
    mockApi({
      "/bank-review/queue": {
        ...QUEUE,
        items: [],
        stats: { ...QUEUE.stats, waiting: 0, overdue: 0, average_hours_to_decide: null },
      },
    });
    renderWithProviders(<ReviewDesk />);
    expect(await screen.findByText("Nothing is waiting for the bank")).toBeInTheDocument();
    expect(screen.getByText("none yet")).toBeInTheDocument();
  });
});
