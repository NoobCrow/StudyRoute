import { vi } from "vitest";

/** What the mocked next/navigation hooks return. Tests change these, then render. */
export const navigation = {
  pathname: "/",
  search: "",
  router: {
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  },
};

export function setLocation(pathname: string, search = ""): void {
  navigation.pathname = pathname;
  navigation.search = search;
}

export function resetNavigation(): void {
  navigation.pathname = "/";
  navigation.search = "";
  for (const fn of Object.values(navigation.router)) fn.mockReset();
}
