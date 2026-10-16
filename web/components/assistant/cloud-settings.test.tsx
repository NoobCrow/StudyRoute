import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { WaitNotice } from "@/components/assistant/cloud-settings";
import type { CloudAvailability } from "@/lib/api/types";
import { chatReply, mockApi, problem } from "@/tests/fixtures";
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
  const button = screen.getByRole("button", { name: "Test and save connection" });
  expect(button).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(button);
}

async function ask(text: string) {
  await userEvent.type(screen.getByLabelText("Your question"), text);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

function connectionStore(
  options: { rejected?: boolean; quota?: boolean; deleteFails?: boolean } = {},
) {
  let saved = false;
  return (init?: RequestInit) => {
    if (init?.method === "PUT") {
      if (options.rejected)
        return {
          ok: false,
          saved: false,
          availability: {
            ...LIMITED,
            provider: "groq",
            code: "invalid_key",
            message: "Key rejected",
          },
        };
      saved = true;
      return {
        ok: true,
        saved,
        provider: "groq",
        model: "test-model",
        verified: !options.quota,
        ...(options.quota ? { availability: LIMITED } : {}),
      };
    }
    if (init?.method === "DELETE") {
      if (options.deleteFails) return problem(503, "UNAVAILABLE", "Could not remove key");
      saved = false;
    }
    return saved
      ? { saved, provider: "groq", model: "test-model", verified: !options.quota }
      : { saved };
  };
}

function requests(fetch: ReturnType<typeof mockApi>, path: string) {
  return fetch.mock.calls.filter(([url]) => String(url).endsWith(path));
}

describe("saved cloud connection", () => {
  it("requires consent, saves explicitly and never puts keys in chat or browser storage", async () => {
    const fetch = mockApi({
      "/assistant/connection": connectionStore(),
      "/assistant/chat": chatReply({ reply: "Model reply", mode: "llm" }),
    });
    panel();
    await ask("hello");
    await screen.findByText("Model reply");
    await enterKey();
    await screen.findByText(/Connected to groq/);
    expect(screen.getByLabelText("API key")).toHaveValue("");
    const save = requests(fetch, "/assistant/connection").find(
      ([, init]) => init?.method === "PUT",
    );
    expect(JSON.parse(String(save?.[1]?.body))).toEqual({
      provider: "groq",
      api_key: TEST_KEY,
      consent: true,
      storage_consent: true,
    });
    await ask("What do you do?");
    await vi.waitFor(() => expect(requests(fetch, "/assistant/chat")).toHaveLength(2));
    const request = JSON.parse(String(requests(fetch, "/assistant/chat")[1]?.[1]?.body));
    expect(request.connection).toBeUndefined();
    expect(JSON.stringify(request)).not.toContain(TEST_KEY);
    expect(request.context.conversation).toEqual([
      { role: "user", text: "hello" },
      { role: "assistant", text: "Model reply" },
    ]);
    expect(document.body.textContent).not.toContain(TEST_KEY);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(TEST_KEY);
  });

  it("restores saved metadata after remount without re-entering or retrieving a key", async () => {
    const fetch = mockApi({
      "/assistant/connection": connectionStore(),
      "/assistant/chat": chatReply({ reply: "Restored answer" }),
    });
    const first = panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    first.unmount();
    panel("session-b");
    await screen.findByText(/Connected to groq/);
    expect(screen.getByLabelText("API key")).toHaveValue("");
    await ask("hello");
    await screen.findByText("Restored answer");
    expect(
      requests(fetch, "/assistant/connection").filter(([, i]) => i?.method === "PUT"),
    ).toHaveLength(1);
    expect(
      JSON.parse(String(requests(fetch, "/assistant/chat")[0]?.[1]?.body)).connection,
    ).toBeUndefined();
  });

  it("never activates a rejected key", async () => {
    mockApi({ "/assistant/connection": connectionStore({ rejected: true }) });
    panel();
    await enterKey();
    await screen.findByText("Key rejected");
    expect(screen.queryByText(/Connected to groq/)).toBeNull();
  });

  it("removes the server key while preserving the conversation", async () => {
    const fetch = mockApi({
      "/assistant/connection": connectionStore(),
      "/assistant/chat": chatReply({ reply: "Reply kept" }),
    });
    panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    await ask("hello");
    await screen.findByText("Reply kept");
    await userEvent.click(
      screen.getByRole("button", { name: "Remove saved key and use default provider" }),
    );
    await vi.waitFor(() => expect(screen.queryByText(/Connected to groq/)).toBeNull());
    expect(screen.getByText("Reply kept")).toBeInTheDocument();
    expect(requests(fetch, "/assistant/connection").some(([, i]) => i?.method === "DELETE")).toBe(
      true,
    );
  });

  it("does not pretend the saved key was removed if the server fails", async () => {
    mockApi({ "/assistant/connection": connectionStore({ deleteFails: true }) });
    panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    await userEvent.click(
      screen.getByRole("button", { name: "Remove saved key and use default provider" }),
    );
    await screen.findByText("Could not remove key");
    expect(screen.getByText(/Connected to groq/)).toBeInTheDocument();
  });

  it("labels a quota-limited saved key as unverified, not a successful provider test", async () => {
    mockApi({ "/assistant/connection": connectionStore({ quota: true }) });
    panel();
    await enterKey();
    await screen.findByText(/Key saved, but the provider test was not verified/);
    expect(screen.queryByText(/Connection verified and saved/)).toBeNull();
    expect(screen.getByText("Free GPU quota reached.")).toBeInTheDocument();
  });

  it("does not let a stale initial metadata fetch overwrite a successful save", async () => {
    let release: (value: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: unknown, init?: RequestInit) => {
        if (init?.method === "GET")
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        return new Response(
          JSON.stringify({
            ok: true,
            saved: true,
            provider: "groq",
            model: "test-model",
            verified: true,
          }),
        );
      }),
    );
    panel();
    await enterKey();
    await screen.findByText(/Connected to groq/);
    await act(async () => {
      release(new Response(JSON.stringify({ saved: false })));
    });
    expect(screen.getByText(/Connected to groq/)).toBeInTheDocument();
  });

  it("opens key controls on quota failure without a silent template", async () => {
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
