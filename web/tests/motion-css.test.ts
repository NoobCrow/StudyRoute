import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// The motion lives in the stylesheet (the production policy forbids inline styles). These checks keep
// it safe and honest: every animation token has its keyframes, people who ask for less motion get none,
// and the stylesheet never reaches for another site.
const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

describe("app/globals.css motion", () => {
  it("defines the keyframes behind every animate-* token", () => {
    const tokens = [...css.matchAll(/--animate-[\w-]+:\s*([\w-]+)\s/g)].map((m) => m[1]);
    expect(tokens.length).toBeGreaterThan(10);
    for (const name of tokens) {
      expect(css, `@keyframes ${name}`).toMatch(new RegExp(`@keyframes ${name}\\s*\\{`));
    }
  });

  it("removes every duration and delay for people who ask for reduced motion", () => {
    const block = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/animation-delay:\s*0ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
  });

  it("staggers up to eleven children and caps the rest, with no inline delay needed", () => {
    for (let n = 1; n <= 11; n += 1) {
      expect(css).toContain(`.stagger > :nth-child(${n})`);
    }
    expect(css).toContain(".stagger > :nth-child(n + 12)");
  });

  it("loads nothing from another site (no remote url, no import over the network)", () => {
    expect(css).not.toMatch(/url\(\s*["']?https?:/i);
    expect(css).not.toMatch(/@import\s+(url\()?["']?https?:/i);
  });

  it("keeps the slider, shimmer and theme fade rules the components rely on", () => {
    for (const rule of [".range", ".skeleton-shimmer", ".app-glow", "html.theme-fade"]) {
      expect(css, rule).toContain(rule);
    }
  });
});
