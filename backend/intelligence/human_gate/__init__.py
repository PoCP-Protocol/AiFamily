"""Human confirmation boundary for AI-generated drafts.

The package deliberately stops at a ``NamedActionRequest``.  A request is a
message to the owning business domain; it is not a domain fact and this
package has no repository, session, or ORM dependency with which to write one.
"""

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanDecision,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.human_gate.persistence import (
    HUMAN_TASKS_TABLE,
    HumanGateBase,
    HumanTaskRow,
    SqlAlchemyHumanGate,
)

__all__ = [
    "ActionProposal",
    "ActorType",
    "DecisionOutcome",
    "GateScope",
    "GateStatus",
    "HumanDecision",
    "HumanGateError",
    "HumanTask",
    "InMemoryHumanGate",
    "HUMAN_TASKS_TABLE",
    "HumanGateBase",
    "HumanTaskRow",
    "SqlAlchemyHumanGate",
    "NamedActionRequest",
]
