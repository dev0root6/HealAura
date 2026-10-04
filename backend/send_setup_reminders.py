"""One-off: email existing accounts that haven't finished profile setup.

Each account is reminded at most once (users.setup_reminder_sent_at). Accounts
without an email can't be emailed; they see the in-app "Finish setting up" prompt.

Usage (from backend/): python send_setup_reminders.py [--dry-run]
"""

import asyncio
import sys

import db
import email_client
import emails


async def main(dry_run: bool) -> None:
    await db.init_db()
    pending = await db.users_needing_setup_reminder()
    print(f"{len(pending)} account(s) to remind")
    for user in pending:
        if dry_run:
            print(f"  would email {user['username']}")
            continue
        subject, text, html = emails.setup_reminder(user["username"])
        try:
            await email_client.send_email(user["email"], subject, text, html)
            await db.mark_setup_reminder_sent(user["id"])
            print(f"  reminded {user['username']}")
        except RuntimeError as exc:
            print(f"  could not email {user['username']}: {exc}")
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
