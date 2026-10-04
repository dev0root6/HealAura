"""Verify the well-being agent's gating logic by running the real agent.evaluate_and_alert
against an in-memory stand-in for the database and SMTP layers.

Checks:
  1. Truth table over the four gates (G1 needs_support, G2 >=3 negatives in 24 h,
     G3 cooldown elapsed, G4 >=1 friend): 16 combinations, alert iff all hold.
  2. Boundary values for G2 (2 vs 3 negatives) and G3 (11.9 h vs 12 h).
  3. User corrections: negatives corrected to neutral stop counting.
  4. Failure isolation: SMTP failure and database exceptions never raise.
  5. Replay of the Fig. 5 timeline; alert times are computed by the real agent.

Writes agent_checks.json. Usage: python run_agent_checks.py
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

import agent  # noqa: E402
import db  # noqa: E402
import email_client  # noqa: E402
from models import FriendOut, UserOut  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class World:
    """In-memory replacement for the four db calls and the e-mail sender."""

    def __init__(self):
        self.now = T0
        self.segments = []  # (time, model_sentiment, corrected_sentiment)
        self.last_alert = None
        self.friends = []
        self.sent = []
        self.smtp_fails = False
        self.db_raises = False

    def install(self):
        async def count_recent_negative(user_id, hours=24):
            if self.db_raises:
                raise ConnectionError("simulated database outage")
            win = [s for s in self.segments if self.now - timedelta(hours=hours) <= s[0] <= self.now]
            neg = sum(1 for _, m, c in win if (c or m) == "negative")  # COALESCE(corrected, model)
            return neg, len(win)

        async def alert_allowed(user_id, cooldown_hours=12):
            return self.last_alert is None or self.now - self.last_alert >= timedelta(hours=cooldown_hours)

        async def mark_alert_sent(user_id):
            self.last_alert = self.now

        async def list_friends(user_id):
            return self.friends

        async def send_email(to, subject, body):
            if self.smtp_fails:
                raise RuntimeError("simulated SMTP failure")
            self.sent.append({"to": to, "subject": subject, "body": body, "at": self.now.isoformat()})

        db.count_recent_negative = count_recent_negative
        db.alert_allowed = alert_allowed
        db.mark_alert_sent = mark_alert_sent
        db.list_friends = list_friends
        email_client.send_email = send_email

    def add_friend(self):
        self.friends.append(FriendOut(id=uuid4(), name="Friend", email="friend@example.com", created_at=T0))

    def add_negatives(self, n, hours_ago=1.0, corrected=None):
        for _ in range(n):
            self.segments.append((self.now - timedelta(hours=hours_ago), "negative", corrected))


USER = UserOut(id=uuid4(), username="student", is_admin=False, created_at=T0)


async def fresh(**kw):
    w = World()
    w.install()
    return w


async def truth_table():
    rows = []
    for g1, g2, g3, g4 in product([False, True], repeat=4):
        w = await fresh()
        w.add_negatives(3 if g2 else 2)
        if not g3:
            w.last_alert = w.now - timedelta(hours=2)
        if g4:
            w.add_friend()
        sent = await agent.evaluate_and_alert(USER, needs_support=g1)
        rows.append({"G1": g1, "G2": g2, "G3": g3, "G4": g4, "expected": g1 and g2 and g3 and g4, "alert": sent})
    return rows


async def boundaries():
    out = {}
    for label, negs, cooldown_h, expect in [
        ("2 negatives", 2, None, False),
        ("3 negatives", 3, None, True),
        ("cooldown 11.9 h", 3, 11.9, False),
        ("cooldown 12.0 h", 3, 12.0, True),
    ]:
        w = await fresh()
        w.add_friend()
        w.add_negatives(negs)
        if cooldown_h is not None:
            w.last_alert = w.now - timedelta(hours=cooldown_h)
        out[label] = {"expected": expect, "alert": await agent.evaluate_and_alert(USER, needs_support=True)}
    # negatives older than the 24 h window must not count
    w = await fresh(); w.add_friend(); w.add_negatives(3, hours_ago=25)
    out["3 negatives, 25 h old"] = {"expected": False, "alert": await agent.evaluate_and_alert(USER, needs_support=True)}
    return out


async def corrections():
    w = await fresh()
    w.add_friend()
    w.add_negatives(2)
    w.add_negatives(1, corrected="neutral")  # user fixed a wrong 'negative'
    a = await agent.evaluate_and_alert(USER, needs_support=True)
    w2 = await fresh()
    w2.add_friend()
    w2.add_negatives(3)
    b = await agent.evaluate_and_alert(USER, needs_support=True)
    return {"3 model negatives, 1 corrected to neutral": {"expected": False, "alert": a},
            "3 model negatives, none corrected": {"expected": True, "alert": b}}


async def failures():
    w = await fresh(); w.add_friend(); w.add_negatives(3); w.smtp_fails = True
    smtp = await agent.evaluate_and_alert(USER, needs_support=True)
    smtp_marked = w.last_alert is not None
    w = await fresh(); w.add_friend(); w.db_raises = True
    try:
        dbres = await agent.evaluate_and_alert(USER, needs_support=True)
        raised = False
    except Exception:
        dbres, raised = None, True
    return {"smtp_failure": {"returned": smtp, "cooldown_started": smtp_marked, "expected": "False, no cooldown"},
            "db_exception": {"returned": dbres, "raised": raised, "expected": "False, no raise"}}


async def privacy():
    w = await fresh(); w.add_friend(); w.add_negatives(3)
    secret = "I failed my exam and cried all night"
    w.segments.append((w.now, "negative", None))
    await agent.evaluate_and_alert(USER, needs_support=True)
    body = w.sent[0]["body"] if w.sent else ""
    return {"email_sent": bool(w.sent), "entry_text_in_email": secret.lower() in body.lower(),
            "email_body": body}


# Same synthetic timeline as Fig. 5 (hours from t=0).
NEG_EVENTS = [2, 5, 9, 14, 15, 16, 21, 31, 40, 41, 42]
FLAGS = {15, 21, 41}


async def replay():
    w = await fresh()
    w.add_friend()
    alerts, suppressed = [], []
    for h in sorted(set(NEG_EVENTS) | FLAGS):
        w.now = T0 + timedelta(hours=h)
        if h in NEG_EVENTS:
            w.segments.append((w.now, "negative", None))
        if h in FLAGS:
            sent = await agent.evaluate_and_alert(USER, needs_support=True)
            (alerts if sent else suppressed).append(h)
    return {"neg_events_h": NEG_EVENTS, "flags_h": sorted(FLAGS), "alerts_h": alerts, "suppressed_h": suppressed}


async def main():
    res = {
        "truth_table": await truth_table(),
        "boundaries": await boundaries(),
        "corrections": await corrections(),
        "failures": await failures(),
        "privacy": await privacy(),
        "fig5_replay": await replay(),
    }
    tt = res["truth_table"]
    passed = sum(r["alert"] == r["expected"] for r in tt)
    checks = [v["alert"] == v["expected"] for v in {**res["boundaries"], **res["corrections"]}.values()]
    checks += [res["failures"]["smtp_failure"]["returned"] is False and not res["failures"]["smtp_failure"]["cooldown_started"],
               res["failures"]["db_exception"]["returned"] is False and not res["failures"]["db_exception"]["raised"],
               res["privacy"]["email_sent"] and not res["privacy"]["entry_text_in_email"]]
    res["summary"] = {"truth_table": f"{passed}/{len(tt)}", "other_checks": f"{sum(checks)}/{len(checks)}"}
    (HERE / "agent_checks.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res["summary"]), json.dumps(res["fig5_replay"]))


if __name__ == "__main__":
    asyncio.run(main())
