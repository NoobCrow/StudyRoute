import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MfaDialog } from "@/components/payment/mfa-dialog";
import { mockApi, problem } from "@/tests/fixtures";

afterEach(() => vi.unstubAllGlobals());

function open(sandboxCode?: string) {
  const onProof = vi.fn();
  const onCancel = vi.fn();
  render(
    <MfaDialog
      title="Approve this payment"
      scope="approve_payment"
      subjectId="pay_1"
      sandboxCode={sandboxCode}
      onProof={onProof}
      onCancel={onCancel}
    />,
  );
  return { onProof, onCancel };
}

describe("MFA dialog", () => {
  it("asks for the code and says the proof is short-lived and single-use", async () => {
    open();
    expect(await screen.findByRole("dialog", { name: "Approve this payment" })).toBeInTheDocument();
    expect(screen.getByLabelText("MFA code")).toBeInTheDocument();
    expect(screen.getByText(/lasts 5 minutes and works once/)).toBeInTheDocument();
  });

  it("binds the proof to the action and the subject, and hands it on", async () => {
    const fetchMock = mockApi({ "/auth/mfa/verify": { mfa_proof: "proof_123" } });
    const { onProof } = open();
    await userEvent.type(await screen.findByLabelText("MFA code"), " 246810 ");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await vi.waitFor(() => expect(onProof).toHaveBeenCalledWith("proof_123"));
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, string>;
    expect(body).toEqual({ code: "246810", scope: "approve_payment", subject_id: "pay_1" });
  });

  it("explains a too-short code before anything is sent", async () => {
    const fetchMock = mockApi({});
    const { onProof } = open();
    await userEvent.type(await screen.findByLabelText("MFA code"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(
      await screen.findByText("Enter the code from your authenticator app."),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onProof).not.toHaveBeenCalled();
  });

  it("shows the server's refusal and stays open when the code is wrong", async () => {
    mockApi({ "/auth/mfa/verify": problem(401, "MFA_INVALID", "That code is not valid.") });
    const { onProof } = open();
    await userEvent.type(await screen.findByLabelText("MFA code"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    expect(onProof).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("calls cancel from the Cancel button and from Escape", async () => {
    const { onCancel } = open();
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("shows the demo code only when the sandbox gives it", async () => {
    open("246810");
    expect(await screen.findByText("246810")).toBeInTheDocument();
    expect(screen.getByText(/Sandbox hint/)).toBeInTheDocument();
  });
});
