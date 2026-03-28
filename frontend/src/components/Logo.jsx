export default function Logo({ size = 32, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="logo-bg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#4338ca" />
        </linearGradient>
      </defs>
      {/* Rounded square background */}
      <rect width="32" height="32" rx="8" fill="url(#logo-bg)" />
      {/* RSS dot */}
      <circle cx="9.5" cy="23.5" r="2.5" fill="white" />
      {/* Inner arc */}
      <path
        d="M9.5 17.5 a8 8 0 0 1 8 8"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      {/* Outer arc */}
      <path
        d="M9.5 11 a14 14 0 0 1 14 14"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
