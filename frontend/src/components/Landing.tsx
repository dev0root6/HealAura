import { HeartHandshake, MessageCircleHeart, Users, Heart } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import Logo from './Logo'

interface LandingProps {
  onSignIn: () => void
  onSignUp: () => void
}

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: MessageCircleHeart,
    title: 'Talk with AI',
    text: 'Journal by voice or text. A gentle companion listens and reflects back.',
  },
  {
    icon: Users,
    title: 'Community',
    text: 'Share anonymously with people who get it. No names, no profiles.',
  },
  {
    icon: HeartHandshake,
    title: 'Counsellors',
    text: 'Reach trained professionals in your language when you need more.',
  },
  {
    icon: Heart,
    title: 'Close friends',
    text: 'If things get heavy, a caring agent quietly nudges the friends you trust.',
  },
]

export default function Landing({ onSignIn, onSignUp }: LandingProps) {
  return (
    <div className="landing">
      <div className="glow" aria-hidden="true" />
      <nav className="landing-nav">
        <span className="brand-lockup">
          <Logo size={38} />
          <span className="brand">HealAura</span>
        </span>
        <div className="landing-actions">
          <button type="button" className="ghost" onClick={onSignIn}>
            Sign in
          </button>
          <button type="button" className="primary" onClick={onSignUp}>
            Sign up
          </button>
        </div>
      </nav>

      <section className="hero">
        <p className="eyebrow">Daily reflection, gently guided</p>
        <h1>
          A softer place
          <br />
          to land each day.
        </h1>
        <p className="hero-sub">
          HealAura turns a few honest words into understanding — and, when you need
          it, quietly rallies the people who care about you.
        </p>
        <button type="button" className="primary big" onClick={onSignUp}>
          Get started
        </button>
        <p className="muted small">It's a reflection aid, not a medical treatment.</p>
      </section>

      <section className="feature-grid">
        {FEATURES.map((f) => (
          <div key={f.title} className="glass feature">
            <span className="feature-icon" aria-hidden="true">
              <f.icon size={22} />
            </span>
            <h3>{f.title}</h3>
            <p>{f.text}</p>
          </div>
        ))}
      </section>

      <footer className="landing-foot muted small">
        Built for reflection and connection · Demo build
      </footer>
    </div>
  )
}
