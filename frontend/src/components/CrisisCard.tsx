// Shown immediately when an entry mentions self-harm or suicide. It does not
// wait for the well-being agent's thresholds, and it never auto-dials anyone.
//
// Numbers are India-wide services. Verify them before any real deployment.
const HELPLINES = [
  { name: 'Tele-MANAS', detail: 'Free, 24×7 mental health support · many Indian languages', tel: '14416' },
  { name: 'Tele-MANAS (alt.)', detail: 'Toll-free line', tel: '1-800-891-4416' },
  { name: 'Emergency', detail: 'Police · ambulance · immediate danger', tel: '112' },
]

interface CrisisCardProps {
  onOpenCounsellors: () => void
  onOpenFriends: () => void
}

export default function CrisisCard({ onOpenCounsellors, onOpenFriends }: CrisisCardProps) {
  return (
    <div className="crisis-card" role="alert">
      <p className="crisis-title">You don't have to go through this alone.</p>
      <p className="crisis-body">
        If you're thinking about ending your life or hurting yourself, please reach out to someone
        right now. These lines are free and confidential.
      </p>
      <ul className="crisis-lines">
        {HELPLINES.map((h) => (
          <li key={h.tel}>
            <a className="crisis-call" href={`tel:${h.tel.replace(/-/g, '')}`}>
              <span className="crisis-name">{h.name}</span>
              <span className="crisis-tel">{h.tel}</span>
            </a>
            <span className="crisis-detail">{h.detail}</span>
          </li>
        ))}
      </ul>
      <div className="crisis-actions">
        <button type="button" className="chip" onClick={onOpenCounsellors}>
          Talk to a counsellor
        </button>
        <button type="button" className="chip" onClick={onOpenFriends}>
          Reach a close friend
        </button>
      </div>
    </div>
  )
}
