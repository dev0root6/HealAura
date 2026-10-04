"""Automated well-being agent.

After each entry, this looks at the user's recent emotional context. Only when
the signals point to sustained distress (not a single bad moment), or to an
explicit crisis, does it reach out: a check-in email to the user themselves
(with helplines) and a nudge to the close friends they opted to list. It never
shares what was written. A cooldown stops it from messaging repeatedly.
"""

import logging
from datetime import datetime, timedelta, timezone

import db
import email_client
import emails
from models import UserOut

logger = logging.getLogger(__name__)

# Sustained distress, not a one-off: several negative segments in a day, and the
# latest entry itself tripped the support signal.
_MIN_NEGATIVES = 3
_WINDOW_HOURS = 24
COOLDOWN_HOURS = 12
# A crisis has its own, much shorter cooldown: it must never be silenced by an
# earlier ordinary check-in, only kept from emailing friends on every message.
CRISIS_COOLDOWN_MINUTES = 60


async def evaluate_and_alert(
    user: UserOut, *, needs_support: bool, crisis: bool = False
) -> bool:
    """Decide whether to alert the user's close friends. Returns True if sent.

    A crisis (explicit self-harm or suicide disclosure) skips the sustained-
    negativity gate and the 12-hour cooldown: it is only held back if another
    crisis alert went out in the last hour.

    Failures here never propagate — the journaling flow must not break because an
    email could not be sent.
    """
    try:
        if not (needs_support or crisis):
            return False

        if not crisis:
            negatives, _total = await db.count_recent_negative(user.id, _WINDOW_HOURS)
            if negatives < _MIN_NEGATIVES:
                logger.info(
                    "No alert for %s: support signal but only %d/%d negative moments in %dh",
                    user.username, negatives, _MIN_NEGATIVES, _WINDOW_HOURS,
                )
                return False

        if crisis:
            last = await db.last_alert_with_reason(user.id, "crisis")
            if last and datetime.now(timezone.utc) - last < timedelta(minutes=CRISIS_COOLDOWN_MINUTES):
                logger.info(
                    "No alert for %s: a crisis alert already went out in the last %d min",
                    user.username, CRISIS_COOLDOWN_MINUTES,
                )
                return False
        elif not await db.alert_allowed(user.id, COOLDOWN_HOURS):
            logger.info("No alert for %s: within the %dh cooldown", user.username, COOLDOWN_HOURS)
            return False

        return await send_alert(user, reason="crisis" if crisis else "sustained")
    except Exception:  # never let the agent break the entry flow
        logger.exception("Agent evaluation failed for %s", getattr(user, "username", "?"))
        return False


async def send_alert(user: UserOut, *, reason: str) -> bool:
    """Email the user's close friends and the user. Records the outcome. True if any email went out.

    reason: "crisis" (urgent wording), "sustained", or "test" (a clearly labelled
    test that also tells friends they were added).
    """
    friends = await db.list_friends(user.id)
    if not friends and not user.email:
        logger.info("No alert for %s: no close friends and no email on the account", user.username)
        return False

    sent_friends = failed_friends = 0
    for friend in friends:
        if reason == "test":
            subject, text, html = emails.friend_test(friend.name, user.username)
        else:
            subject, text, html = emails.friend_check_in(friend.name, user.username, urgent=reason == "crisis")
        try:
            await email_client.send_email(friend.email, subject, text, html)
            sent_friends += 1
        except RuntimeError as exc:
            failed_friends += 1
            logger.warning("Could not email close friend of %s: %s", user.username, exc)

    # The user hears from HealAura too (helplines, and whether friends were
    # nudged), so nothing is done behind their back. Tests skip this.
    sent_self = False
    if user.email and reason != "test":
        subject, text, html = emails.self_check_in(user.username, friends_notified=sent_friends > 0)
        try:
            await email_client.send_email(user.email, subject, text, html)
            sent_self = True
        except RuntimeError as exc:
            logger.warning("Could not send check-in to %s: %s", user.username, exc)

    sent_any = sent_friends > 0 or sent_self
    await db.record_alert(user.id, reason, sent_friends, failed_friends, sent_self)
    if sent_any and reason != "test":
        await db.mark_alert_sent(user.id)
    logger.info(
        "Well-being alert (%s) for %s: %d friend(s) emailed, %d failed, self=%s",
        reason, user.username, sent_friends, failed_friends, sent_self,
    )
    return sent_any
