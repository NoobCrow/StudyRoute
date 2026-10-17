import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AssistantSheet } from "@/components/layout/assistant-sheet";
import type { ChatResponse } from "@/lib/api/types";
import { chatReply, mockApi } from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

afterEach(() => vi.unstubAllGlobals());

async function askOnce(reply: ChatResponse) {
  mockApi({ "/assistant/chat": reply });
  renderWithProviders(
    <AssistantProvider>
      <AssistantSheet open onOpenChange={() => undefined} />
    </AssistantProvider>,
  );
  await userEvent.type(screen.getByLabelText("Your question"), "Which provider is cheapest?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("AssistantSheet model chip", () => {
  it("names the small trained model that rewrote the engine's answer", async () => {
    await askOnce(
      chatReply({ mode: "llm", provider: "local", model_version: "studyroute-explainer-v1" }),
    );
    expect(await screen.findByText("Trained explainer")).toBeInTheDocument();
    expect(screen.queryByText(/Model: /)).not.toBeInTheDocument();
  });

  it("still shows the model version for an external model", async () => {
    await askOnce(chatReply({ mode: "llm", provider: "groq", model_version: "test-model" }));
    expect(await screen.findByText("Model: test-model")).toBeInTheDocument();
    expect(screen.queryByText("Trained explainer")).not.toBeInTheDocument();
  });

  it("says the assistant is offline when the engine's own template answered", async () => {
    await askOnce(chatReply());
    expect(await screen.findByText("Offline assistant")).toBeInTheDocument();
  });
});
