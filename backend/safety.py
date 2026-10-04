"""Crisis detection for explicit self-harm or suicide disclosures.

The well-being agent waits for *sustained* distress before reaching out, which is
right for ordinary bad days and wrong for a message like "I want to end my
life". This module flags those messages so the app can show crisis resources
and alert trusted friends immediately.

Two signals are combined:
  - the model's own `crisis` judgement from the reply call, and
  - a deterministic phrase list, so a crisis is still caught when the model is
    unreachable, returns plain text, or misses it.

People often disguise these words (moderation habits from social media):
"SU1c1de", "s.u.i.c.i.d.e", "$uicide", "k!ll mys3lf", "unalive". The text is
normalised before matching so those are caught too. The list errs towards
recall: a false positive shows a helpline card and nudges a friend; a false
negative could miss someone in danger.
"""

import re

# Look-alike characters people swap in, mapped back to letters.
_LEET = str.maketrans({
    "0": "o", "1": "i", "!": "i", "|": "i", "3": "e", "4": "a", "@": "a",
    "5": "s", "$": "s", "7": "t", "+": "t", "8": "b", "9": "g",
})

# Lower-cased, matched on word boundaries against normalised text. English plus
# common romanised Tamil (Tanglish) and Hindi (Hinglish) phrasings.
_CRISIS_PHRASES = [
    # English
    r"kill myself", r"killing myself", r"end my life", r"ending my life", r"end myself",
    r"take my (own )?life", r"want to die", r"wanna die", r"wish i (was|were) dead",
    r"better off dead", r"suicid\w*", r"sucide", r"self[- ]?harm", r"hurt myself", r"cut myself",
    r"no reason to live", r"don'?t want to (live|be alive)", r"end it all",
    r"unalive( myself)?", r"kms",
    # Tanglish
    r"saaga(nu|num|ponen|poren|lam)", r"sethu(ranum|duven|poiduven|pogalam)",
    r"thar?kolai", r"uyira? vida(num|poren|lam)", r"vazha pidikkala",
    # Hinglish
    r"mar ja(na|naa|unga|aun|ana)", r"marna chah(ta|ti)", r"khud ?kushi",
    r"aatm ?hatya", r"jeena nahi chah(ta|ti)", r"zindagi khatam",
]
_CRISIS_RE = re.compile(r"\b(" + "|".join(_CRISIS_PHRASES) + r")")
# Words written with separators between every letter: "s u i c i d e", "s.u.i.c.i.d.e".
_SPACED_RE = re.compile(r"\b(?:[a-z][\s.\-_*]){3,}[a-z]\b")


def _normalise(text: str) -> list[str]:
    """Variants of the text to match against: plain, de-leeted, and de-spaced."""
    lowered = (text or "").lower()
    unleet = lowered.translate(_LEET)
    despaced = _SPACED_RE.sub(lambda m: re.sub(r"[\s.\-_*]", "", m.group(0)), unleet)
    # "suuuicide", "kiiill" -> collapse runs of 3+ identical letters to one.
    squeezed = re.sub(r"([a-z])\1{2,}", r"\1", despaced)
    return [lowered, unleet, despaced, squeezed]


def matches_crisis_phrase(text: str) -> bool:
    """True if the text contains an explicit self-harm or suicide phrase, even disguised."""
    return any(_CRISIS_RE.search(variant) for variant in _normalise(text))


def is_crisis(text: str, model_flag: bool) -> bool:
    """Combine the model's judgement with the phrase safety net."""
    return model_flag or matches_crisis_phrase(text)
