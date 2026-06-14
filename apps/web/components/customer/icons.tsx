import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const common = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function MicIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6" />
    </svg>
  );
}

export function PhoneOffIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m3 3 18 18M8.5 8.5a16 16 0 0 0-2 3.5c2.4 4.4 5.1 6.9 9.5 9l3-3-3.8-3.8-2.2 1.3M15.5 7.5 18 5l3 3-1.5 1.5" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M12 3 4.5 6v5.5c0 4.5 3 7.8 7.5 9.5 4.5-1.7 7.5-5 7.5-9.5V6Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function DocumentIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M6 2h8l4 4v16H6Z" />
      <path d="M14 2v5h5M9 12h6M9 16h6" />
    </svg>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

