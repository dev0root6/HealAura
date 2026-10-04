"""Automated well-being agent.

After each entry, this looks at the user's recent emotional context. Only when
the signals point to sustained distress (not a single bad moment), or to an
explicit crisis, does it reach out: a check-in email to the user themselves
(with helplines) and a nudge to the close friends they opted to list. It never
shares what was written. A cooldown stops it from messaging repeatedly.
"""

import logging

import db
import email_client
import emails
from models import UserOut

logger = logging.getLogger(__name__)

# Sustained distress, not a one-off: several negative segments in a day, and the
# latest entry itself tripped the support signal.
_MIN_NEGATIVES = 3
_WINDOW_HOURS = 24
_COOLDOWN_HOURS = 12


async def evaluate_and_alert(
    user: UserOut, *, needs_support: bool, crisis: bool = False
) -> bool:
    """Decide whether to alert the user's close friends. Returns True if sent.

    A crisis (explicit self-harm or suicide disclosure) skips the sustained-
    negativity gate: waiting for three negative segments is wrong there. The
    cooldown and the opt-in friend list still apply.

    Failures here never propagate — the journaling flow must not break because an
    email could not be sent.
    """
    try:
        if not (needs_support or crisis):
            return False

        if not crisis:
            negatives, _total = await db.count_recent_negative(user.id, _WINDOW_HOURS)
            if negatives < _MIN_NEGATIVES:
                return False

        if not await db.alert_allowed(user.id, _COOLDOWN_HOURS):
            logger.info("Alert suppressed for %s (cooldown)", user.username)
            return False

        friends = await db.list_friends(user.id)
        if not friends and not user.email:
            return False

        sent_friends = 0
        for friend in friends:
            subject, text, html = emails.friend_check_in(friend.name, user.username, urgent=crisis)
            try:
                await email_client.send_email(friend.email, subject, text, html)
                sent_friends += 1
            except RuntimeError as exc:
                logger.warning("Could not alert %s: %s", friend.email, exc)

        # The user hears from HealAura too, with helplines, and is told
        # whether their friends were nudged; nothing is done behind their back.
        sent_self = False
        if user.email:
            subject, text, html = emails.self_check_in(user.username, friends_notified=sent_friends > 0)
            try:
                await email_client.send_email(user.email, subject, text, html)
                sent_self = True
            except RuntimeError as exc:
                logger.warning("Could not send check-in to %s: %s", user.username, exc)

        sent_any = sent_friends > 0 or sent_self
        if sent_any:
            await db.mark_alert_sent(user.id)
            logger.info(
                "Well-being alert for %s: %d friend(s), self=%s", user.username, sent_friends, sent_self
            )
        return sent_any
    except Exception:  # never let the agent break the entry flow
        logger.exception("Agent evaluation failed for %s", getattr(user, "username", "?"))
        return False
