#!/usr/bin/env python3
"""
Email classifier for forget-the-thunderdome (ftt) IMAP provider.

Factored into its own module so the keyword rules are unit-testable in
isolation (see the verify snippet in docs/providers/imap-setup.md).

The category set and keyword rules intentionally MIRROR the Gmail reference
implementation in mcp-servers/gmail-server/gmail_tracker.py::classify_email so
that every provider produces the SAME `email_type` values feeding the pipeline:

    interview_invite | offer | rejection | recruiter_outreach |
    application_update | other

NOTE (future refactor): the Gmail server has its own private copy of these
rules. A future change could lift this module to a shared location (e.g.
src/) and have every provider import it, retiring the duplicate. We do NOT
edit gmail_tracker.py to share code today, to keep providers decoupled.

This variant takes `sender` in addition to subject/body. Sender is currently
only used as a light tie-breaker for recruiter outreach (recruiter/talent/
careers-style From addresses), but is part of the signature so provider code
and future rules can use it without a breaking change.
"""

from typing import Optional

# Ordered most-specific → least-specific. The first matching category wins,
# mirroring the precedence in the Gmail reference classifier.
REJECTION_KEYWORDS = [
    'unfortunately', 'not moving forward', 'decided to move on',
    'not a fit', 'other candidates', 'position has been filled',
    'will not be moving forward', 'regret to inform',
]
OFFER_KEYWORDS = [
    'offer', 'pleased to offer', 'compensation package', 'start date',
]
INTERVIEW_KEYWORDS = [
    'interview', 'phone screen', 'technical screen', 'meet with',
    'schedule time', 'schedule a call', 'schedule a time',
]
APPLICATION_UPDATE_KEYWORDS = [
    'received your application', 'application confirmed',
    'thank you for applying', 'we have received', 'application received',
]
RECRUITER_KEYWORDS = [
    'opportunity', 'exciting role', 'came across your profile',
    'thought you might be', 'open to hearing', 'are you interested',
    'reaching out', 'your background',
]

# Light sender-domain hints for recruiter outreach.
RECRUITER_SENDER_HINTS = [
    'recruit', 'talent', 'careers', 'hiring', 'hr@', 'ta@',
    'greenhouse.io', 'lever.co', 'ashbyhq.com', 'jobvite.com',
    'workable.com', 'smartrecruiters.com',
]


def classify_email(subject: str, sender: Optional[str], body: Optional[str]) -> str:
    """Classify an email into a pipeline `email_type`.

    Args:
        subject: The email Subject header (may be empty).
        sender:  The From header / address (may be empty or None). Used only as
                 a tie-breaker for recruiter outreach.
        body:    The plain-text body (may be empty or None). Only the first
                 ~300 chars are considered, matching the Gmail reference.

    Returns one of:
        interview_invite, offer, rejection, recruiter_outreach,
        application_update, other
    """
    subject = subject or ''
    body = body or ''
    sender = sender or ''
    text = f"{subject} {body[:300]}".lower()

    if any(w in text for w in REJECTION_KEYWORDS):
        return 'rejection'
    if any(w in text for w in OFFER_KEYWORDS):
        return 'offer'
    if any(w in text for w in INTERVIEW_KEYWORDS):
        return 'interview_invite'
    if any(w in text for w in APPLICATION_UPDATE_KEYWORDS):
        return 'application_update'
    if any(w in text for w in RECRUITER_KEYWORDS):
        return 'recruiter_outreach'

    # Fall back to a sender-domain hint before giving up.
    sender_l = sender.lower()
    if any(hint in sender_l for hint in RECRUITER_SENDER_HINTS):
        return 'recruiter_outreach'

    return 'other'


if __name__ == '__main__':
    # Tiny self-check so `python3 classify.py` demonstrates discrimination.
    samples = [
        ('Interview invitation for Senior Engineer', 'recruiter@acme.com',
         'We would love to schedule a call'),
        ('Update on your application', 'no-reply@acme.com',
         'Unfortunately we will not be moving forward'),
        ('Your offer from Example Corp', 'hr@example.com',
         'We are pleased to offer you the role, start date TBD'),
        ('Thank you for applying', 'jobs@acme.com',
         'We have received your application'),
        ('A role you might like', 'talent@acme.com',
         'I came across your profile and thought you might be interested'),
        ('Lunch tomorrow?', 'friend@gmail.com', 'Wanna grab food'),
    ]
    for subj, snd, bdy in samples:
        print(f"{classify_email(subj, snd, bdy):<20} | {subj}")
