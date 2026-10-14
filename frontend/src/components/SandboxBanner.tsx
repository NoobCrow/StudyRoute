export const SANDBOX_TEXT = "Sandbox - synthetic data - no real money moves";

/** Shown on every screen, including the sign-in page. */
export function SandboxBanner() {
  return (
    <section className="sandbox-banner" aria-label="Sandbox notice">
      {SANDBOX_TEXT}
      <span className="pill">Indicative only. Confirm with your AD bank.</span>
    </section>
  );
}
