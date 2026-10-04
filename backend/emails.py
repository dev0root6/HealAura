"""Email content HealAura sends: sign-up codes and well-being check-ins.

Each builder returns (subject, plain_text, html). The HTML is deliberately
simple inline-styled markup that renders in Gmail, Outlook and phone clients.
Nothing here ever includes what a user wrote in their journal.
"""

from html import escape

_HELPLINES_TEXT = (
    "Tele-MANAS (free, 24x7): 14416 or 1-800-891-4416\n"
    "Emergency: 112"
)


def _wrap(title: str, inner: str) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#fff6ef;font-family:'Plus Jakarta Sans',Segoe UI,Roboto,Arial,sans-serif;color:#3a2a22">
  <table role="presentation" width="100%" style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;padding:28px;border:1px solid #ffe0d6">
    <tr><td>
      <p style="margin:0 0 4px;font-size:22px;font-weight:700;color:#ff5a5f">HealAura</p>
      <p style="margin:0 0 20px;font-size:13px;color:#8a7266">{escape(title)}</p>
      {inner}
      <p style="margin:24px 0 0;font-size:12px;color:#8a7266">HealAura is a reflection aid, not a medical service.</p>
    </td></tr>
  </table>
</body></html>"""


def verification_code(code: str, minutes: int) -> tuple[str, str, str]:
    subject = f"Your HealAura code: {code}"
    text = (
        f"Your HealAura verification code is {code}\n\n"
        f"It expires in {minutes} minutes. If you didn't try to sign up, you can ignore this email."
    )
    html = _wrap(
        "Verify your email",
        f"""<p style="margin:0 0 12px;font-size:15px">Here's your code to finish signing up:</p>
      <p style="margin:0 0 16px;font-size:34px;font-weight:700;letter-spacing:8px;color:#241812">{escape(code)}</p>
      <p style="margin:0;font-size:14px;color:#8a7266">It expires in {minutes} minutes. If you didn't try to sign up, you can ignore this email.</p>""",
    )
    return subject, text, html


def friend_check_in(friend_name: str, username: str, urgent: bool) -> tuple[str, str, str]:
    subject = (
        "Please check in on your friend today" if urgent else "A friend of yours could use some support"
    )
    when = "today, if you can" if urgent else "sometime soon"
    text = (
        f"Hi {friend_name},\n\n"
        f"{username} has been going through a hard time lately. They use HealAura, a daily "
        f"reflection app, and listed you as someone they trust.\n\n"
        f"We're not sharing anything they wrote, just a nudge that a kind check-in from you, "
        f"{when}, might mean a lot.\n\n"
        f"If you think they are in immediate danger, call 112.\n\n— HealAura"
    )
    html = _wrap(
        "A gentle nudge from someone who trusts you",
        f"""<p style="margin:0 0 12px;font-size:15px">Hi {escape(friend_name)},</p>
      <p style="margin:0 0 12px;font-size:15px"><strong>{escape(username)}</strong> has been going through a hard time lately. They use HealAura, a daily reflection app, and listed you as someone they trust.</p>
      <p style="margin:0 0 12px;font-size:15px">We're not sharing anything they wrote, just a nudge that a kind check-in from you, {when}, might mean a lot.</p>
      <p style="margin:0;font-size:13px;color:#8a7266">If you think they are in immediate danger, call 112.</p>""",
    )
    return subject, text, html


def self_check_in(username: str, friends_notified: bool) -> tuple[str, str, str]:
    subject = "We're thinking of you"
    told = (
        "We've also let the close friends you listed know that a check-in might help. "
        "We didn't share anything you wrote.\n\n"
        if friends_notified
        else ""
    )
    text = (
        f"Hi {username},\n\n"
        f"It sounds like things have been heavy lately. You don't have to carry it alone.\n\n"
        f"{told}"
        f"If you'd like to talk to someone right now:\n{_HELPLINES_TEXT}\n\n— HealAura"
    )
    told_html = (
        "<p style=\"margin:0 0 12px;font-size:15px\">We've also let the close friends you listed know "
        "that a check-in might help. We didn't share anything you wrote.</p>"
        if friends_notified
        else ""
    )
    html = _wrap(
        "Checking in",
        f"""<p style="margin:0 0 12px;font-size:15px">Hi {escape(username)},</p>
      <p style="margin:0 0 12px;font-size:15px">It sounds like things have been heavy lately. You don't have to carry it alone.</p>
      {told_html}
      <p style="margin:0 0 6px;font-size:15px">If you'd like to talk to someone right now:</p>
      <p style="margin:0;font-size:15px"><strong>Tele-MANAS</strong> (free, 24x7): <a href="tel:14416" style="color:#d1435b">14416</a> or <a href="tel:18008914416" style="color:#d1435b">1-800-891-4416</a><br>
      <strong>Emergency</strong>: <a href="tel:112" style="color:#d1435b">112</a></p>""",
    )
    return subject, text, html
