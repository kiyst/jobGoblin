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
_LOCATION_RECORDS: list[CaseRecord] = _ALL_RECORDS["location"]


@pytest.mark.parametrize("record", _LOCATION_RECORDS, ids=[r.record_id for r in _LOCATION_RECORDS])
def test_location_contract_case(record: CaseRecord) -> None:
    run_case(record)


def test_location_contract_corpus_covers_every_active_guard() -> None:
    from tests.contracts.taxonomy import active_guards

    location_guards = {ref for ref, g in active_guards().items() if g.parser == "location"}
    covered = {r.guard_ref for r in _LOCATION_RECORDS if r.is_primary_witness}
    assert covered == location_guards
