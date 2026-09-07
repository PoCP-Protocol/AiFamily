"""OTP delivery adapters implementing `application.ports.OtpSender`.

`StubOtpSender` is the **only** implementation today, and its name says so:
it does not call any SMS/email provider. It exists so `OtpChallenge`
(`domain/entities.py`) has a concrete, honestly-named collaborator to be
constructed with, rather than either (a) no adapter at all, forcing callers to
special-case "OTP is unimplemented", or (b) a plausible-looking fake that logs
nothing and could be mistaken for a working integration.

Swapping this for a real provider (Twilio, SES, a domestic SMS gateway, ...)
is meant to be a pure adapter replacement: implement `OtpSender.send`, wire it
in the composition root instead of `StubOtpSender`, change nothing in
`application/service.py` or the domain layer. See `domain/entities.py`'s
`OtpChallenge` docstring for why the provider choice itself is out of scope
here.
"""

from __future__ import annotations

import logging

from ..domain.entities import OtpChallenge

logger = logging.getLogger("backend.domains.identity.otp")


class StubOtpSender:
    """Records that a challenge *would* be sent; sends nothing.

    Logs at INFO with the challenge id and destination's channel only — never
    the code itself, so this stays safe to leave enabled in a shared dev
    environment without leaking a live OTP into logs.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, challenge: OtpChallenge) -> None:
        self.sent.append(challenge.challenge_id)
        logger.info(
            "StubOtpSender: not sending OTP challenge_id=%s channel=%s "
            "(no real provider configured — see OtpSender docstring)",
            challenge.challenge_id,
            challenge.channel,
        )


__all__ = ["StubOtpSender"]
