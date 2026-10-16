import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { chatReply, mockApi } from "../test/fixtures";
import { ChatPanel } from "./ChatPanel";

afterEach(() => vi.unstubAllGlobals());

it("saves legacy provider keys explicitly without browser storage or chat credentials", async () => {
  const key = "gsk_synthetic_legacy_test_only";
  const fetch = mockApi({
    "/assistant/connection": (init: RequestInit | undefined) =>
      init?.method === "PUT"
        ? { ok: true, saved: true, verified: true, model: "legacy-test" }
        : { saved: false },
    "/assistant/chat": chatReply({
      reply: "Connected model answer",
      mode: "llm",
    }),
  });
  render(
    <MemoryRouter>
      <ChatPanel />
    </MemoryRouter>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Ask the assistant" }),
  );
  await userEvent.click(screen.getByText("AI connection settings"));
  await userEvent.selectOptions(screen.getByLabelText("Provider"), "groq");
  expect(screen.getByLabelText("API key")).toHaveAttribute("type", "password");
  await userEvent.type(screen.getByLabelText("API key"), key);
  expect(
    screen.getByRole("button", { name: "Test and save connection" }),
  ).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(
    screen.getByRole("button", { name: "Test and save connection" }),
  );
  await screen.findByText(/Connected to groq/);
  await userEvent.type(screen.getByLabelText("Your question"), "hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Connected model answer");
  const saved = fetch.mock.calls.find(([, i]) => i?.method === "PUT");
  expect(JSON.parse(String(saved?.[1]?.body)).storage_consent).toBe(true);
  const chat = fetch.mock.calls.find(([url]) =>
    String(url).endsWith("/assistant/chat"),
  );
  const body = JSON.parse(String(chat?.[1]?.body));
  expect(body.connection).toBeUndefined();
  expect(JSON.stringify(body.context)).not.toContain(key);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(
    key,
  );
});

it("opens key controls when quota expires and never invents a retry time", async () => {
  mockApi({
    "/assistant/chat": chatReply({
      reply: "Cloud limit reached",
      mode: "unavailable",
      availability: {
        provider: "huggingface",
        code: "quota_exhausted",
        message: "Quota exhausted",
        retry_at: null,
        wait_known: false,
        can_add_key: true,
      },
    }),
  });
  render(
    <MemoryRouter>
      <ChatPanel />
    </MemoryRouter>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Ask the assistant" }),
  );
  await userEvent.type(screen.getByLabelText("Your question"), "hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Quota exhausted");
  expect(screen.getByLabelText("API key")).toBeVisible();
  expect(screen.getByText(/No countdown is available/)).toBeInTheDocument();
});
