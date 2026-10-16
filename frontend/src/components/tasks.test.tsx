import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PLAN_CARD, SEND_PLAN, chatReply, corridor, mockApi } from "../test/fixtures";
import { ChatPanel } from "./ChatPanel";
import { PlanCard } from "./PlanCard";
import { SendPlanCard } from "./SendPlanCard";

afterEach(() => vi.unstubAllGlobals());

const CORRIDORS = [corridor({ account_scheme: "IBAN" })];

describe("PlanCard", () => {
  it("shows what was prepared and what is left, with the draft link for the person", () => {
    render(<MemoryRouter><PlanCard card={PLAN_CARD} /></MemoryRouter>);
    expect(screen.getByText(/Payment plan: GBP 10,000.00 to United Kingdom/)).toBeInTheDocument();
    expect(screen.getByText("Provider B (synthetic)")).toBeInTheDocument();
    expect(screen.getByText("BDT 1,625,300.00")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Provider C (synthetic) may leave the university GBP 35.00 short.");
    const steps = within(screen.getByRole("list", { name: "What is done and what is left" })).getAllByRole("listitem");
    expect(steps).toHaveLength(7);
    expect(steps[0]).toHaveTextContent("(done)");
    expect(steps[2]).toHaveTextContent("(to do)");
    const cta = screen.getByRole("link", { name: "Review and create the draft" });
    expect(cta).toHaveAttribute("href", "/compare?quote=qte_plan1&provider=prov_b");
    expect(screen.getByText(/Only you can approve|approve it with a fresh MFA code/)).toBeInTheDocument();
  });

  it("offers an Open link only for steps that are still to do", () => {
    render(<MemoryRouter><PlanCard card={PLAN_CARD} /></MemoryRouter>);
    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/", "/recipients", "/documents"]);
  });
});

describe("SendPlanCard", () => {
  it("asks the engine in minor units and shows the cheapest way on paper", async () => {
    const fetchMock = mockApi({ "/planner/send-plan": SEND_PLAN });
    render(<SendPlanCard corridors={CORRIDORS} />);
    await userEvent.clear(screen.getByLabelText("Needed each month"));
    await userEvent.type(screen.getByLabelText("Needed each month"), "1,000.50");
    await userEvent.click(screen.getByRole("button", { name: "Compare ways to send" }));
    expect(await screen.findByText("Cheapest on paper")).toBeInTheDocument();
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("monthly_minor=100050");
    expect(url).toContain("months=12");
    expect(url).toContain("currency=GBP");
    expect(screen.getByText("BDT 39,900.00")).toBeInTheDocument();
    expect(screen.getByText(/does not predict exchange rates/)).toBeInTheDocument();
  });

  it("explains a bad number before anything is sent", async () => {
    const fetchMock = mockApi({});
    render(<SendPlanCard corridors={CORRIDORS} />);
    await userEvent.clear(screen.getByLabelText("Months to cover"));
    await userEvent.type(screen.getByLabelText("Months to cover"), "99");
    await userEvent.click(screen.getByRole("button", { name: "Compare ways to send" }));
    expect(await screen.findByText(/whole number from 1 to 60/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("assistant chat", () => {
  async function openChat() {
    await userEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));
  }

  it("sends prior user questions, not generated answers, for a follow-up", async () => {
    const fetchMock = mockApi({ "/assistant/chat": chatReply({ reply: "Mock KYC explanation" }) });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    const input = screen.getByLabelText("Your question");
    await userEvent.type(input, "What is my KYC status?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Mock KYC explanation");
    await userEvent.type(input, "how do I fix it?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body)) as {
      context: { history: string[] };
    };
    expect(body.context.history).toEqual(["What is my KYC status?"]);
  });

  it("turns one sentence into a plan card and does not repeat the proposal as a second link", async () => {
    mockApi({
      "/assistant/chat": chatReply({
        task: PLAN_CARD,
        proposed_actions: [{ tool: "create_draft", args: { quote_id: "qte_plan1", provider_id: "prov_b" }, requires_human: true, missing: ["reference"] }],
      }),
    });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }));
    expect(await screen.findByRole("region", { name: "Payment plan" })).toBeInTheDocument();
    expect(screen.queryByText("Proposal only")).toBeNull();
  });

  it("keeps the plan's quote for the next question", async () => {
    const fetchMock = mockApi({ "/assistant/chat": chatReply({ task: PLAN_CARD }) });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }));
    await screen.findByRole("region", { name: "Payment plan" });
    await userEvent.type(screen.getByLabelText("Your question"), "Why is B cheaper than A?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const second = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body)) as { context: { quote_id: string | null } };
    expect(second.context.quote_id).toBe("qte_plan1");
  });

  it("remembers a task it asked about and sends it back with the next message", async () => {
    const asked = chatReply({
      task: { kind: "payment_plan", status: "needs_input", missing: ["an amount and a currency"],
        collected: { amount_minor: null, currency: null, due_date: null, purpose: "TUITION", months: null, charge_code: "OUR" } },
    });
    const fetchMock = mockApi({ "/assistant/chat": asked });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.type(screen.getByLabelText("Your question"), "I need to pay tuition");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await screen.findByText("I made a quote.");
    await userEvent.type(screen.getByLabelText("Your question"), "GBP 10,000 by 28 October");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const second = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body)) as { context: { pending: { kind: string; purpose: string } | null } };
    expect(second.context.pending).toMatchObject({ kind: "payment_plan", purpose: "TUITION" });
  });

  it("shows how the message was read: the intent, how sure the model was and each marked word", async () => {
    mockApi({
      "/assistant/chat": chatReply({
        understanding: {
          source: "trained", model: "studyroute-nlu-v1", model_sha256: "94146e8c4b72", intent: "PLAN", model_intent: "PLAN",
          confidence: 0.97, attack: false, out_of_scope: false, continued_earlier_task: false,
          spans: [
            { label: "AMOUNT", text: "ten thousand", start: 8, end: 20 },
            { label: "CURRENCY", text: "pounds", start: 21, end: 27 },
          ],
          values: { amount_minor: 1000000, currency: "GBP", due_date: null, months: null, charge_code: "OUR", purpose: "TUITION" },
          conflicts: ["amount"], unreadable: ["DATE:soon"],
        },
      }),
    });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }));
    await userEvent.click(await screen.findByText(/How I read this \(trained reader\)/));
    expect(screen.getByText("Reader: studyroute-nlu-v1")).toBeInTheDocument();
    expect(screen.getByText(/97% sure/)).toBeInTheDocument();
    expect(screen.getByText("ten thousand")).toBeInTheDocument();
    expect(screen.getByText(/the reader and the rules read the amount differently, so I left it empty/)).toBeInTheDocument();
    expect(screen.getByText(/I could not read "soon" as a date/)).toBeInTheDocument();
  });

  it("reads the values back and sends yes with what it held when the person confirms", async () => {
    const readBack = chatReply({
      task: { kind: "payment_plan", status: "needs_confirmation", text: "GBP 10,000.00 for tuition",
        collected: { amount_minor: 1000000, currency: "GBP", due_date: "2026-10-28", purpose: "TUITION", months: null,
          charge_code: "OUR", turns: 1, asked: [false, false, false], awaiting_confirmation: true, extra_amount: true } },
      dialogue: { policy: "studyroute-dm-v1", sha256: "abc123abc123", action: "CONFIRM", scores: { CONFIRM: 1.1, RUN: 1.0 } },
    });
    const fetchMock = mockApi({ "/assistant/chat": readBack });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.type(screen.getByLabelText("Your question"), "pay GBP 10,000 by 28 October");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const yes = await screen.findByRole("button", { name: "Yes, plan it" });
    expect(screen.getByRole("button", { name: "No, change something" })).toBeInTheDocument();
    await userEvent.click(yes);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const second = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body)) as { message: string; context: { pending: { awaiting_confirmation: boolean; amount_minor: number } } };
    expect(second.message).toBe("yes");
    expect(second.context.pending).toMatchObject({ awaiting_confirmation: true, amount_minor: 1000000 });
  });

  it("says which step the dialogue policy chose and that it was learned", async () => {
    mockApi({
      "/assistant/chat": chatReply({
        dialogue: { policy: "studyroute-dm-v1", sha256: "abc123abc123", action: "ASK_DATE", scores: { ASK_DATE: 1.2, RUN: 1.1 } },
      }),
    });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "I need to pay GBP 10,000 tuition by 28 October" }));
    await userEvent.click(await screen.findByText(/How I read this/));
    expect(screen.getByText(/chose to ask for the date/)).toBeInTheDocument();
    expect(screen.getByText(/reinforcement learning/)).toBeInTheDocument();
  });

  it("shows the send plan table for a how-often question", async () => {
    mockApi({ "/assistant/chat": chatReply({ task: { kind: "send_plan", status: "ready", plan: SEND_PLAN } }) });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "How often should I send GBP 800 a month for 9 months?" }));
    expect(await screen.findByRole("region", { name: "Send plan" })).toBeInTheDocument();
    expect(screen.getByText("Cheapest on paper")).toBeInTheDocument();
  });
});
