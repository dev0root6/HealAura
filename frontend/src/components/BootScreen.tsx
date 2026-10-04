import Logo from './Logo'

interface BootScreenProps {
  /** True once the app is ready; the screen plays its exit and then unmounts. */
  leaving?: boolean
}

const WORD = 'HealAura'
const ORBITERS = 10

/**
 * Loading screen: a drifting aurora, ripples breathing out of the logo, a
 * heart that beats, a pulse that draws itself, and sparks in orbit. Under
 * prefers-reduced-motion everything holds still (see index.css).
 */
export default function BootScreen({ leaving = false }: BootScreenProps) {
  return (
    <div className={`boot${leaving ? ' boot-leaving' : ''}`} role="status" aria-label="Loading HealAura">
      <div className="boot-aurora" aria-hidden="true">
        <span className="blob blob-1" />
        <span className="blob blob-2" />
        <span className="blob blob-3" />
      </div>

      <div className="boot-stage" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className="boot-ripple" style={{ animationDelay: `${i * 0.9}s` }} />
        ))}
        <div className="boot-orbit">
          {Array.from({ length: ORBITERS }, (_, i) => (
            <span
              key={i}
              className="boot-orbiter"
              style={
                {
                  '--angle': `${(360 / ORBITERS) * i}deg`,
                  '--radius': `${118 + (i % 3) * 22}px`,
                  '--speed': `${7 + (i % 4) * 2.5}s`,
                  '--size': `${4 + (i % 3) * 2}px`,
                } as React.CSSProperties
              }
            />
          ))}
        </div>
        <Logo size={168} animated className="boot-logo" />
      </div>

      <p className="boot-word" aria-hidden="true">
        {WORD.split('').map((ch, i) => (
          <span key={i} style={{ animationDelay: `${0.35 + i * 0.07}s` }}>
            {ch}
          </span>
        ))}
      </p>
      <p className="boot-breath" aria-hidden="true">
        <span className="in">breathe in</span>
        <span className="out">breathe out</span>
      </p>
    </div>
  )
}
