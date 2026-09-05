"""Using a UnitOfWork outside its `async with` block must raise — under `-O` too.

`docs/06_platform/PERSISTENCE.md` §3 gap 6: `commit` / `rollback` / `ping` each
guarded `self.session is not None` with `assert`. `python -O` strips assert
statements, so in an optimised interpreter all three guards vanished and the
failure degraded into `AttributeError: 'NoneType' object has no attribute
'commit'` — a misleading error, and for `commit` a silent no-op risk if a caller
ever caught AttributeError.

The last test in this file is the one that bites: it re-runs the check in a
subprocess with `-O`, which is the only way to prove the guard is not an
`assert`. A test that merely expects "some exception" passes either way, because
`AssertionError` is an exception too.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from backend.platform.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
    UnitOfWorkStateError,
)


@pytest.mark.parametrize("operation", ["commit", "rollback", "ping"])
async def test_operation_outside_the_block_raises_a_state_error(operation: str) -> None:
    uow = SqlAlchemyUnitOfWork()

    with pytest.raises(UnitOfWorkStateError) as excinfo:
        await getattr(uow, operation)()

    assert operation in str(excinfo.value)


async def test_the_error_is_not_an_assertion_error() -> None:
    """`AssertionError` here would mean the guard is still an `assert`."""
    uow = SqlAlchemyUnitOfWork()

    with pytest.raises(UnitOfWorkStateError) as excinfo:
        await uow.commit()

    assert not isinstance(excinfo.value, AssertionError)


async def test_session_is_cleared_after_the_block_so_reuse_is_caught() -> None:
    """Not just "before first use": a UoW reused after exit must also refuse."""
    uow = SqlAlchemyUnitOfWork()
    async with uow:
        pass

    with pytest.raises(UnitOfWorkStateError):
        await uow.commit()


_PROBE = """
import asyncio
import sys

from backend.platform.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
    UnitOfWorkStateError,
)

assert False, "asserts are still enabled — the -O flag did not take effect"
"""

_PROBE_BODY = """
async def main() -> None:
    for operation in ("commit", "rollback", "ping"):
        uow = SqlAlchemyUnitOfWork()
        try:
            await getattr(uow, operation)()
        except UnitOfWorkStateError:
            continue
        except AttributeError as exc:
            raise SystemExit(f"GUARD_STRIPPED:{operation}:{exc}") from exc
        raise SystemExit(f"NO_ERROR_AT_ALL:{operation}")
    print("GUARDS_HELD")


asyncio.run(main())
"""


def test_guards_still_fire_under_python_dash_oh() -> None:
    """Run the same check in `python -O`, where `assert` statements do not exist.

    The subprocess first asserts False. Under `-O` that statement is removed, so
    reaching the rest of the script is itself the proof the flag took effect — if
    the interpreter ever stopped honouring `-O`, this test would fail on the
    probe rather than silently testing nothing.
    """
    result = subprocess.run(
        [sys.executable, "-O", "-c", _PROBE + _PROBE_BODY],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "GUARDS_HELD" in result.stdout
