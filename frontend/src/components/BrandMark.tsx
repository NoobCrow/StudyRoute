/** The StudyRoute mark: a green tile, a route line and a red dot (the same shapes as favicon.svg). */
export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect className="tile" width="32" height="32" rx="9" />
      <path className="route" d="M8 21l5-8 4 5 3-4 4 7" />
      <circle className="dot" cx="25" cy="8" r="2.6" />
    </svg>
  );
}
