import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { WaitNotice } from "@/components/assistant/cloud-settings";
import type { CloudAvailability } from "@/lib/api/types";
import { chatReply, mockApi } from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

const TEST_KEY = "gsk_synthetic_test_key_only";
const LIMITED: CloudAvailability = {
  provider: "huggingface",
  code: "quota_exhausted",
  message: "Free GPU quota reached.",
  retry_at: null,
  wait_known: false,
  can_add_key: true,
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function panel(key = "session-a") {
  return renderWithProviders(
    <AssistantProvider key={key}>
      <AssistantPanel />
    </AssistantProvider>,
  );
}

async function enterKey() {
  await userEvent.click(screen.getByText("AI connection settings"));
  await userEvent.selectOptions(screen.getByLabelText("Provider"), "groq");
  const input = screen.getByLabelText("API key");
  expect(input).toHaveAttribute("type", "password");
  await userEvent.type(input, TEST_KEY);
  const button = screen.getByRole("button", { name: "Test and connect" });
  expect(button).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(button);
}

async function ask(text: string) {
  await userEvent.type(screen.getByLabelText("Your question"), text);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("cloud connection", () => {
  it("requires consent, tests a masked key, keeps it out of history and browser storage", async () => {
    const fetch = mockApi({
      "/assistant/connection/test": { ok: true, provider: "groq", model: "test-model" },
      "/assistant/chat": chatReply({ reply: "Model reply", mode: "llm" }),
    });
    panel();
    await ask("hello");
    await screen.findByText("Model reply");
    await enterKey();
    await screen.findByText(/Connected to groq/);
    expect(screen.getByLabelText("API key")).toHaveValue("");
    await ask("What do you do?");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    const request = JSON.parse(String(fetch.mock.calls[2]?.[1]?.body));
    expect(request.connection).toEqual({ provider: "groq", api_key: TEST_KEY, consent: true });
    expect(JSON.stringify(request.context)).not.toContain(TEST_KEY);
    expect(request.context.conversation).toEqual([
      { role: "user", text: "hello" },
      { role: "assistant", text: "Model reply" },
    ]);
    expect(document.body.textContent).not.toContain(TEST_KEY);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(TEST_KEY);
  });

  it("never activates a rejected key or changes provider automatically", async () => {
    const fetch = mockApi({
      "/assistant/connection/test": {
        ok: false,
        availability: {
          ...LIMITED,
          provider: "groq",
          code: "invalid_key",
          message: "Key rejected",
        },
      },
      "/assistant/chat": chatReply({ reply: "Default reply" }),
    });
    panel();
    await enterKey();
    await screen.findByText("Key rejected");
    expect(screen.queryByText(/Connected to groq/)).toBeNull();
    await ask("hello");
    await screen.findByText("Default reply");
    expect(JSON.parse(String(fetch.mock.calls[1]?.[1]?.body)).connection).toBeUndefined();
  });

  it("removes the key while preserving the conversation", async () => {
    const fetch = mockApi({
      "/assistant/connection/test": { ok: true, model: "test-model" },
      "/assistant/chat": chatReply({ reply: "Reply kept" }),
    });
    panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    await ask("hello");
    await screen.findByText("Reply kept");
    await userEvent.click(
      screen.getByRole("button", { name: "Remove key and use default provider" }),
    );
    expect(screen.getByText("Reply kept")).toBeInTheDocument();
    await ask("continue");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetch.mock.calls[2]?.[1]?.body)).connection).toBeUndefined();
  });

  it("clears key and conversation on a new signed-in session boundary", async () => {
    const fetch = mockApi({
      "/assistant/connection/test": { ok: true, model: "test-model" },
      "/assistant/chat": chatReply({ reply: "Session reply" }),
    });
    const first = panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    first.unmount();
    panel("session-b");
    expect(screen.queryByText(/Connected to groq/)).toBeNull();
    await ask("hello");
    await screen.findByText("Session reply");
    expect(JSON.parse(String(fetch.mock.calls[1]?.[1]?.body)).connection).toBeUndefined();
  });

  it("shows quota failure and opens key input without a silent template", async () => {
    mockApi({
      "/assistant/chat": chatReply({
        reply: "No model response",
        mode: "unavailable",
        availability: LIMITED,
        guard: { status: "cloud_unavailable", failure: "quota_exhausted", flags: [], retries: 0 },
      }),
    });
    panel();
    await ask("hello");
    await screen.findByText("Free GPU quota reached.");
    expect(screen.getByLabelText("API key")).toBeVisible();
    expect(screen.getByText(/did not supply an exact retry time/)).toBeInTheDocument();
    expect(screen.queryByText(/engine's template answer/)).toBeNull();
  });
});

describe("provider-reported retry time", () => {
  it("counts down a supplied deadline, stops at zero and never retries automatically", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-16T12:00:00Z"));
    render(
      <WaitNotice
        availability={{ ...LIMITED, wait_known: true, retry_at: "2026-10-16T12:01:05Z" }}
      />,
    );
    expect(screen.getByText(/1m 5s remaining/)).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText(/1m 0s remaining/)).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(60000));
    expect(screen.getByText(/reported wait has ended/)).toBeInTheDocument();
  });
  it("does not invent a deadline for unknown or malformed provider times", () => {
    render(<WaitNotice availability={{ ...LIMITED, retry_at: "not-a-date" }} />);
    expect(screen.getByText(/No countdown is available/)).toBeInTheDocument();
  });
});
