import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

const confirm = () => screen.getByRole("button", { name: "Confirm" });

describe("MFA dialog", () => {
  it("asks for the code in six boxes and says the proof is short-lived and single-use", async () => {
    open();
    expect(await screen.findByRole("dialog", { name: "Approve this payment" })).toBeInTheDocument();
    const input = screen.getByLabelText("MFA code");
    expect(input).toHaveAttribute("maxlength", "6");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(document.querySelectorAll("[data-slot=input-otp-slot]")).toHaveLength(6);
    expect(screen.getByText(/lasts 5 minutes and works once/)).toBeInTheDocument();
  });

  it("puts the cursor in the code field as soon as it opens", async () => {
    open();
    expect(await screen.findByLabelText("MFA code")).toHaveFocus();
  });

  it("keeps Confirm disabled until all six digits are in", async () => {
    open();
    const input = await screen.findByLabelText("MFA code");
    expect(confirm()).toBeDisabled();
    await userEvent.type(input, "24681");
    expect(confirm()).toBeDisabled();
    await userEvent.type(input, "0");
    expect(confirm()).toBeEnabled();
  });

  it("accepts digits only", async () => {
    open();
    const input = await screen.findByLabelText("MFA code");
    await userEvent.type(input, "12ab-34");
    expect(input).toHaveValue("1234");
  });

  it("takes a pasted code", async () => {
    open();
    await userEvent.click(await screen.findByLabelText("MFA code"));
    await userEvent.paste("246810");
    expect(screen.getByLabelText("MFA code")).toHaveValue("246810");
    expect(confirm()).toBeEnabled();
  });

  it("binds the proof to the action and the subject, and hands it on", async () => {
    const fetchMock = mockApi({ "/auth/mfa/verify": { mfa_proof: "proof_123" } });
    const { onProof } = open();
    await userEvent.type(await screen.findByLabelText("MFA code"), "246810");
    await userEvent.click(confirm());
    await vi.waitFor(() => expect(onProof).toHaveBeenCalledWith("proof_123"));
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, string>;
    expect(body).toEqual({ code: "246810", scope: "approve_payment", subject_id: "pay_1" });
  });

  it("shows the server's refusal, clears the boxes and stays open when the code is wrong", async () => {
    mockApi({ "/auth/mfa/verify": problem(401, "MFA_INVALID", "That code is not valid.") });
    const { onProof } = open();
    const input = await screen.findByLabelText("MFA code");
    await userEvent.type(input, "000000");
    await userEvent.click(confirm());
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    expect(onProof).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(confirm()).toBeDisabled();
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

  it("gives focus back to the button that opened it", async () => {
    function Host() {
      const [shown, setShown] = useState(false);
      return (
        <>
          <button onClick={() => setShown(true)}>Allowlist with MFA</button>
          {shown ? (
            <MfaDialog
              title="Allowlist this recipient"
              scope="allowlist_recipient"
              subjectId="rcp_1"
              onProof={vi.fn()}
              onCancel={() => setShown(false)}
            />
          ) : null}
        </>
      );
    }
    render(<Host />);
    const trigger = screen.getByRole("button", { name: "Allowlist with MFA" });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await vi.waitFor(() => expect(trigger).toHaveFocus());
  });
});
