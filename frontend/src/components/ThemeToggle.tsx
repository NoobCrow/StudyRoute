import { useState } from "react";

import { THEME_LABEL, applyTheme, nextTheme, readTheme, saveTheme } from "../theme";
import type { ThemeChoice } from "../theme";

/** Cycles Auto, Light, Dark. Auto follows the browser's own setting. */
export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(readTheme);

  function cycle() {
    const next = nextTheme(choice);
    applyTheme(next);
    saveTheme(next);
    setChoice(next);
  }

  return (
    <button type="button" className="btn small ghost theme-toggle" onClick={cycle}>
      Theme: {THEME_LABEL[choice]}
    </button>
  );
}
