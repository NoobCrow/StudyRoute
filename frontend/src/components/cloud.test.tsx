import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { chatReply, mockApi } from "../test/fixtures";
import { ChatPanel } from "./ChatPanel";

afterEach(() => vi.unstubAllGlobals());

it("supports request-scoped provider keys in legacy chat without persisting them", async () => {
  const key = "gsk_synthetic_legacy_test_only";
  const fetch = mockApi({
    "/assistant/connection/test": { ok: true, model: "legacy-test" },
    "/assistant/chat": chatReply({ reply: "Connected model answer", mode: "llm" }),
  });
  render(<MemoryRouter><ChatPanel /></MemoryRouter>);
  await userEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));
  await userEvent.click(screen.getByText("AI connection settings"));
  await userEvent.selectOptions(screen.getByLabelText("Provider"), "groq");
  expect(screen.getByLabelText("API key")).toHaveAttribute("type", "password");
  await userEvent.type(screen.getByLabelText("API key"), key);
  expect(screen.getByRole("button", { name: "Test and connect" })).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Test and connect" }));
  await screen.findByText(/Connected to groq/);
  await userEvent.type(screen.getByLabelText("Your question"), "hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Connected model answer");
  const body = JSON.parse(String(fetch.mock.calls[1]?.[1]?.body));
  expect(body.connection.api_key).toBe(key);
  expect(JSON.stringify(body.context)).not.toContain(key);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(key);
});

it("opens key controls when quota expires and never invents a retry time", async () => {
  mockApi({ "/assistant/chat": chatReply({
    reply: "Cloud limit reached", mode: "unavailable", availability: {
      provider: "huggingface", code: "quota_exhausted", message: "Quota exhausted",
      retry_at: null, wait_known: false, can_add_key: true,
    },
  }) });
  render(<MemoryRouter><ChatPanel /></MemoryRouter>);
  await userEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));
  await userEvent.type(screen.getByLabelText("Your question"), "hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Quota exhausted");
  expect(screen.getByLabelText("API key")).toBeVisible();
  expect(screen.getByText(/No countdown is available/)).toBeInTheDocument();
});
