import pytest

from backend.workflow_worker.family_need_event_reader import (
    SqlAlchemyFamilyNeedEventReader,
)


def test_reader_requires_sqlalchemy_async_engine():
    with pytest.raises(TypeError, match="AsyncEngine"):
        SqlAlchemyFamilyNeedEventReader(object())
