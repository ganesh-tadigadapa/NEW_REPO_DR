import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// next/link and next/navigation expect the App Router to be mounted. These tests render
// components directly, so both are stubbed down to what the components actually use.
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: any) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/screen",
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
