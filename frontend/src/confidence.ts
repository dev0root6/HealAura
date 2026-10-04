import type { Entry } from './api'

// Below this self-consistency score the repeated classifications disagreed,
// so the card asks the user rather than assuming.
const UNSURE_BELOW = 0.75

/** True when the model was unsure about this segment and the user hasn't checked it. */
export function isUnsure(entry: Entry): boolean {
  return (
    entry.user_confirmed !== 1 &&
    entry.ai_confidence !== null &&
    entry.ai_confidence < UNSURE_BELOW
  )
}
