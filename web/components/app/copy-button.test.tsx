import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopyButton } from "@/components/app/copy-button";

afterEach(() => vi.restoreAllMocks());

describe("CopyButton", () => {
  it("copies the value and then says it was copied", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<CopyButton value="UETR-123" label="UETR" />);

    await user.click(screen.getByRole("button", { name: "Copy UETR" }));

    expect(writeText).toHaveBeenCalledWith("UETR-123");
    expect(await screen.findByRole("button", { name: "UETR copied" })).toBeInTheDocument();
  });

  it("does not claim success when the browser refuses the clipboard", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("blocked"));
    render(<CopyButton value="UETR-123" label="UETR" />);

    await user.click(screen.getByRole("button", { name: "Copy UETR" }));

    expect(screen.getByRole("button", { name: "Copy UETR" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "UETR copied" })).not.toBeInTheDocument();
  });
});
