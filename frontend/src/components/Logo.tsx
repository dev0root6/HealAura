import { useId } from 'react'

interface LogoProps {
  size?: number
  /** Adds the class hooks the loading screen animates (rings, heart, pulse, sparkles). */
  animated?: boolean
  className?: string
}

/**
 * The HealAura mark: aura rings rippling out from a heart whose pulse settles
 * into an even breath. Same artwork as public/logo.svg and logo.png.
 * Gradient ids are made unique per instance so several logos can share a page.
 */
export default function Logo({ size = 40, animated = false, className }: LogoProps) {
  const id = useId().replace(/:/g, '')
  const warm = `${id}-warm`
  const heart = `${id}-heart`
  const glow = `${id}-glow`
  const shine = `${id}-shine`

  return (
    <svg
      viewBox="0 0 512 512"
      width={size}
      height={size}
      className={`logo${animated ? ' logo-animated' : ''}${className ? ` ${className}` : ''}`}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={warm} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffb04a" />
          <stop offset="0.55" stopColor="#ff7a52" />
          <stop offset="1" stopColor="#ff4f6d" />
        </linearGradient>
        <linearGradient id={heart} x1="0.2" y1="0" x2="0.8" y2="1">
          <stop offset="0" stopColor="#ff9a3c" />
          <stop offset="1" stopColor="#ff4566" />
        </linearGradient>
        <radialGradient id={glow} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#ffd2a8" stopOpacity="0.95" />
          <stop offset="0.6" stopColor="#ffb08a" stopOpacity="0.35" />
          <stop offset="1" stopColor="#ff9a7a" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={shine} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <circle className="ha-glow" cx="256" cy="256" r="250" fill={`url(#${glow})`} />

      <g fill="none" stroke={`url(#${warm})`} strokeLinecap="round">
        <circle className="ha-ring ha-ring-3" cx="256" cy="262" r="214" strokeWidth="7" opacity="0.28" />
        <circle className="ha-ring ha-ring-2" cx="256" cy="259" r="178" strokeWidth="10" opacity="0.5" />
        <path
          className="ha-ring ha-ring-1"
          d="M 120 300 A 142 142 0 1 1 392 300"
          strokeWidth="14"
          opacity="0.9"
        />
      </g>

      <g className="ha-heart">
        <path
          d="M256 384 C 214 350, 150 306, 150 246 C 150 206, 180 178, 216 178 C 236 178, 249 188, 256 202 C 263 188, 276 178, 296 178 C 332 178, 362 206, 362 246 C 362 306, 298 350, 256 384 Z"
          fill={`url(#${heart})`}
        />
        <path
          className="ha-pulse"
          d="M 172 270 L 212 270 Q 220 270 224 260 L 236 228 Q 240 220 244 230 L 262 300 Q 266 310 270 300 L 280 272 Q 283 266 290 266 C 306 266 314 282 330 278 C 336 276 338 272 340 270"
          fill="none"
          stroke="#fff"
          strokeOpacity="0.92"
          strokeWidth="11"
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
        />
        <path
          d="M168 238 C 172 206, 196 192, 222 196"
          fill="none"
          stroke={`url(#${shine})`}
          strokeWidth="12"
          strokeLinecap="round"
        />
      </g>

      <path
        className="ha-spark"
        d="M392 118 l9 25 25 9 -25 9 -9 25 -9 -25 -25 -9 25 -9 z"
        fill="#ffb04a"
      />
      <circle className="ha-spark ha-spark-2" cx="122" cy="142" r="9" fill="#ff7a52" opacity="0.8" />
    </svg>
  )
}
