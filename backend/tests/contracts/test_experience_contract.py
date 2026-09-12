from pathlib import Path

import pytest

from tests.contracts.loader import collect_all
from tests.contracts.runner import run_case
from tests.contracts.schema import CaseRecord

_RECORDS_DIR = Path(__file__).resolve().parent / "records"
_ALL_RECORDS = collect_all(
    {
        "location": _RECORDS_DIR / "location.json",
        "salary": _RECORDS_DIR / "salary.json",
        "experience": _RECORDS_DIR / "experience.json",
    }
)
_EXPERIENCE_RECORDS: list[CaseRecord] = _ALL_RECORDS["experience"]


@pytest.mark.parametrize(
    "record", _EXPERIENCE_RECORDS, ids=[r.record_id for r in _EXPERIENCE_RECORDS]
)
def test_experience_contract_case(record: CaseRecord) -> None:
    run_case(record)


def test_experience_contract_corpus_covers_every_active_guard() -> None:
    from tests.contracts.taxonomy import active_guards

    experience_guards = {ref for ref, g in active_guards().items() if g.parser == "experience"}
    covered = {r.guard_ref for r in _EXPERIENCE_RECORDS if r.is_primary_witness}
    assert covered == experience_guards


def test_experience_g07_is_superseded_with_no_contract_record() -> None:
    from tests.contracts.taxonomy import GUARD_INVENTORY

    guard = GUARD_INVENTORY["experience/g07-reversed-label-anchor"]
    assert guard.status == "superseded"
    assert guard.superseded_by == "experience/g18-description-label-value-scope-removed"
    assert not any(r.guard_ref == guard.guard_ref for r in _EXPERIENCE_RECORDS)
