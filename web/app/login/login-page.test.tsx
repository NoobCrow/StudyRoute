import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import { useAuth } from "@/components/providers/auth-provider";
import { resetHealthCache } from "@/lib/api/health";
import { ApiError } from "@/lib/api/client";
import { PARENT_PERMISSIONS, mockApi, user } from "@/tests/fixtures";
import { navigation } from "@/tests/navigation";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const HEALTH = {
  status: "ok",
  mode: "sandbox",
  ai_mode: "template",
  demo: {
    accounts: ["parent@demo.studyroute.test", "student@demo.studyroute.test"],
    password: "demo-password",
    mfa_code: "246810",
  },
};

function auth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  const value = {
    user: null,
    ready: true,
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(),
    reloadUser: vi.fn(),
    ...overrides,
  };
  vi.mocked(useAuth).mockReturnValue(value);
  return value;
}

beforeEach(() => resetHealthCache());
afterEach(() => vi.unstubAllGlobals());

describe("sign-in page", () => {
  it("explains the product and shows the sandbox hints from the API", async () => {
    auth();
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    expect(screen.getByRole("heading", { name: "Sign in to StudyRoute" })).toBeInTheDocument();
    expect(await screen.findByText("demo-password")).toBeInTheDocument();
    expect(screen.getByText("246810")).toBeInTheDocument();
    expect(screen.getByText(/template mode \(no model key set\)/)).toBeInTheDocument();
  });

  it("asks the team for an account when the API gives no hints", async () => {
    auth();
    mockApi({ "/health": { status: "ok", mode: "production", ai_mode: "template" } });
    renderWithProviders(<LoginPage />);
    expect(await screen.findByText("Ask the team for a demo account.")).toBeInTheDocument();
  });

  it("fills the form from a demo account button", async () => {
    auth();
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "student@demo.studyroute.test" }),
    );
    expect(screen.getByLabelText("Email")).toHaveValue("student@demo.studyroute.test");
    expect(screen.getByLabelText("Password")).toHaveValue("demo-password");
  });

  it("explains each missing field before anything is sent", async () => {
    const value = auth();
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(value.login).not.toHaveBeenCalled();
  });

  it("signs in and goes to the dashboard", async () => {
    const value = auth();
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "parent@demo.studyroute.test");
    await userEvent.type(screen.getByLabelText("Password"), "demo-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() =>
      expect(value.login).toHaveBeenCalledWith("parent@demo.studyroute.test", "demo-password"),
    );
    expect(navigation.router.replace).toHaveBeenCalledWith("/");
  });

  it("shows the server's reason and stays on the page when the password is wrong", async () => {
    const value = auth({
      login: vi
        .fn()
        .mockRejectedValue(
          new ApiError(
            401,
            "INVALID_CREDENTIALS",
            "Sign-in failed",
            "Email or password is wrong.",
            "req_1",
          ),
        ),
    });
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "parent@demo.studyroute.test");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is wrong.");
    expect(value.login).toHaveBeenCalledTimes(1);
    expect(navigation.router.replace).not.toHaveBeenCalled();
  });

  it("sends a person who is already signed in to the dashboard", async () => {
    auth({ user: user("parent", PARENT_PERMISSIONS) });
    mockApi({ "/health": HEALTH });
    renderWithProviders(<LoginPage />);
    await waitFor(() => expect(navigation.router.replace).toHaveBeenCalledWith("/"));
  });
});
