import { render, renderHook, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { Chip, KycBadge, NotVerifiedBadge, StateBadge } from "@/components/app/status";
import { SANDBOX_TEXT, SandboxBanner } from "@/components/layout/sandbox-banner";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { ApiError } from "@/lib/api/client";

describe("status chips", () => {
  it("writes a payment state in words, not codes", () => {
    render(<StateBadge state="PENDING_APPROVAL" />);
    expect(screen.getByText("PENDING APPROVAL")).toBeInTheDocument();
  });

  it("labels every KYC status as simulated", () => {
    const { rerender } = render(<KycBadge status="VERIFIED" />);
    expect(screen.getByText("KYC verified (simulated)")).toBeInTheDocument();
    rerender(<KycBadge status="NEEDS_DOCUMENTS" />);
    expect(screen.getByText("KYC needs documents (simulated)")).toBeInTheDocument();
    rerender(<KycBadge status="PENDING" />);
    expect(screen.getByText("KYC pending (simulated)")).toBeInTheDocument();
  });

  it("explains an unchecked rule on hover", () => {
    render(<NotVerifiedBadge />);
    expect(screen.getByText("Not verified")).toHaveAttribute(
      "title",
      "Not checked against an official source. Confirm with your AD bank.",
    );
  });

  it("renders any tone with its text, so colour is never the only signal", () => {
    render(
      <>
        <Chip tone="ok">Pass</Chip>
        <Chip tone="danger">Fail</Chip>
        <Chip>Plain</Chip>
      </>,
    );
    expect(screen.getByText("Pass")).toBeInTheDocument();
    expect(screen.getByText("Fail")).toBeInTheDocument();
    expect(screen.getByText("Plain")).toBeInTheDocument();
  });
});

describe("notices", () => {
  it("announces danger as an alert and the rest as status", () => {
    render(
      <>
        <Notice tone="danger">Broken</Notice>
        <Notice tone="info">FYI</Notice>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Broken");
    expect(screen.getByRole("status")).toHaveTextContent("FYI");
  });

  it("shows the problem title, code, reason, wait time and request id", () => {
    const error = new ApiError(
      429,
      "RATE_LIMITED",
      "Too many requests",
      "Slow down.",
      "req_9",
      {},
      30,
    );
    render(<ErrorNotice error={error} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Too many requests (RATE_LIMITED)");
    expect(alert).toHaveTextContent("Slow down.");
    expect(alert).toHaveTextContent("Try again in 30 seconds.");
    expect(alert).toHaveTextContent("Request req_9");
  });

  it("shows a plain error's message", () => {
    render(<ErrorNotice error={new Error("Network down")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent("Network down");
  });

  it("offers Retry only when there is something to retry", async () => {
    const retry = vi.fn();
    const { rerender } = render(<ErrorNotice error={new Error("x")} />);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    rerender(<ErrorNotice error={new Error("x")} onRetry={retry} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when there is no error", () => {
    const { container } = render(<ErrorNotice error={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("sandbox banner", () => {
  it("says the data is synthetic and the numbers are indicative", () => {
    render(<SandboxBanner />);
    const banner = screen.getByRole("alert", { name: "Sandbox notice" });
    expect(banner).toHaveTextContent(SANDBOX_TEXT);
    expect(banner).toHaveTextContent("Indicative only. Confirm with your AD bank.");
  });
});

describe("useIdempotencyKey", () => {
  it("keeps the same key while the request is unchanged, so a retry cannot pay twice", () => {
    const { result, rerender } = renderHook(({ fp }) => useIdempotencyKey(fp), {
      initialProps: { fp: "a" },
    });
    const first = result.current;
    rerender({ fp: "a" });
    expect(result.current).toBe(first);
  });

  it("makes a new key when the request changes", () => {
    const { result, rerender } = renderHook(({ fp }) => useIdempotencyKey(fp), {
      initialProps: { fp: "a" },
    });
    const first = result.current;
    act(() => rerender({ fp: "b" }));
    expect(result.current).not.toBe(first);
    expect(result.current).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });
});
