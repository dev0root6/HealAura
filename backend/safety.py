"""Crisis detection for explicit self-harm or suicide disclosures.

The well-being agent waits for *sustained* distress before reaching out, which is
right for ordinary bad days and wrong for a message like "I want to end my
life". This module flags those messages so the app can show crisis resources
immediately, without waiting for any threshold.

Two signals are combined:
  - the model's own `crisis` judgement from the back-channel call, and
  - a deterministic phrase list, so a crisis is still caught when the model is
    unreachable or returns something unparseable (the back-channel then falls
    back to a neutral noise and reports nothing).

The phrase list errs towards recall: a false positive shows a helpline card,
a false negative hides it.
"""

import re

# Lower-cased, matched on word boundaries. English plus common romanised
# Tamil (Tanglish) and Hindi (Hinglish) phrasings.
_CRISIS_PHRASES = [
    # English
    r"kill myself", r"killing myself", r"end my life", r"ending my life",
    r"take my (own )?life", r"want to die", r"wanna die", r"wish i (was|were) dead",
    r"better off dead", r"suicid\w*", r"self[- ]?harm", r"hurt myself", r"cut myself",
    r"no reason to live", r"don'?t want to (live|be alive)", r"end it all",
    # Tanglish
    r"saaga(nu|num|ponen|poren|lam)", r"sethu(ranum|duven|poiduven|pogalam)",
    r"thar?kolai", r"uyira? vida(num|poren|lam)", r"vazha pidikkala",
    # Hinglish
    r"mar ja(na|naa|unga|aun|ana)", r"marna chah(ta|ti)", r"khud ?kushi",
    r"aatm ?hatya", r"jeena nahi chah(ta|ti)", r"zindagi khatam",
]
_CRISIS_RE = re.compile(r"\b(" + "|".join(_CRISIS_PHRASES) + r")", re.IGNORECASE)


def matches_crisis_phrase(text: str) -> bool:
    """True if the text contains an explicit self-harm or suicide phrase."""
    return bool(_CRISIS_RE.search(text or ""))


def is_crisis(text: str, model_flag: bool) -> bool:
    """Combine the model's judgement with the phrase safety net."""
    return model_flag or matches_crisis_phrase(text)
