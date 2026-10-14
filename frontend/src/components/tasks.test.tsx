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

  it("shows the send plan table for a how-often question", async () => {
    mockApi({ "/assistant/chat": chatReply({ task: { kind: "send_plan", status: "ready", plan: SEND_PLAN } }) });
    render(<MemoryRouter><ChatPanel /></MemoryRouter>);
    await openChat();
    await userEvent.click(screen.getByRole("button", { name: "How often should I send GBP 800 a month for 9 months?" }));
    expect(await screen.findByRole("region", { name: "Send plan" })).toBeInTheDocument();
    expect(screen.getByText("Cheapest on paper")).toBeInTheDocument();
  });
});
