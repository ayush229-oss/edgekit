/**
 * Canonical Edgekit logo mark — use this everywhere instead of inline divs/imgs.
 * Renders the SVG icon at a consistent size.
 */
export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <img
      src="/edgekit-logo-icon.svg"
      alt="Edgekit"
      width={size}
      height={size}
      className={`rounded-md shrink-0 ${className}`}
    />
  );
}
