import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import {
  KYC, PARENT_PERMISSIONS, STUDENT_PERMISSIONS, mockApi, payment, user,
} from "../test/fixtures";
import { PaymentScreen } from "./Payment";

vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));

const PREVIEW = { format: "MT103", simulated: true, notes: [], fields: [], pacs008: { ChrgBr: "DEBT", UETR: null, RmtInf: "x" } };
const TRACKER = { payment_id: "pay_1", uetr: null, state: "QUOTED", host_rail: "UK Faster Payments", simulated: true, timeline: [] };
const HEALTH = { status: "ok", mode: "sandbox", demo: { accounts: [], password: "", mfa_code: "246810", parent_id: "usr_parent" } };

function asRole(role: Role, permissions: string[]) {
  vi.mocked(useAuth).mockReturnValue({
    user: user(role, permissions), ready: true, login: vi.fn(), logout: vi.fn(), reloadUser: vi.fn(),
  });
}

function open(data: ReturnType<typeof payment>) {
  const fetchMock = mockApi({
    "/payments/pay_1": data,
    "/payments/pay_1/tracker": TRACKER,
    "/payments/pay_1/instruction-preview": PREVIEW,
    "/kyc/status": KYC,
    "/health": HEALTH,
  });
  render(
    <MemoryRouter initialEntries={["/payments/pay_1"]}>
      <Routes><Route path="/payments/:paymentId" element={<PaymentScreen />} /></Routes>
    </MemoryRouter>,
  );
  return fetchMock;
}

beforeEach(() => asRole("parent", PARENT_PERMISSIONS));
afterEach(() => vi.unstubAllGlobals());

describe("payment screen", () => {
  it("T07: Request approval is disabled and explains why while KYC is not verified", async () => {
    open(payment({
      readiness: {
        blockers: [{ code: "KYC_NOT_VERIFIED", message: "KYC is not verified (simulated)." }],
        can_request_approval: false, can_approve: false,
      },
    }));
    const button = await screen.findByRole("button", { name: "Request approval" });
    expect(button).toBeDisabled();
    expect(await screen.findByText("KYC is not verified (simulated).")).toBeInTheDocument();
    expect(await screen.findByText(/Your documents are being reviewed/)).toBeInTheDocument();
  });

  it("enables Request approval when nothing blocks it", async () => {
    open(payment());
    expect(await screen.findByRole("button", { name: "Request approval" })).toBeEnabled();
  });

  it("opens the MFA step before approving and never approves without it", async () => {
    const data = payment({
      state: "PENDING_APPROVAL", summary_hash: "sha256:abcdef0123456789",
      readiness: { blockers: [], can_request_approval: false, can_approve: true },
    });
    const fetchMock = open(data);
    await userEvent.click(await screen.findByRole("button", { name: "Approve with MFA" }));
    expect(await screen.findByRole("dialog", { name: "Approve this payment" })).toBeInTheDocument();
    const approveCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/approve"));
    expect(approveCalls).toHaveLength(0);
  });

  it("gives the student no way to request approval or approve", async () => {
    asRole("student", STUDENT_PERMISSIONS);
    open(payment());
    await screen.findByText("Actions");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Request approval" })).toBeNull());
    expect(screen.queryByRole("button", { name: "Approve with MFA" })).toBeNull();
    expect(screen.getByText(/Only the paying parent can request approval/)).toBeInTheDocument();
  });

  it("labels a finished payment as simulated and offers no actions", async () => {
    open(payment({ state: "SETTLED", readiness: { blockers: [], can_request_approval: false, can_approve: false } }));
    expect(await screen.findByText("Settled (simulated)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel payment" })).toBeNull();
  });
});
