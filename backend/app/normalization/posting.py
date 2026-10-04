"""Pure, provider-neutral composition of the Phase 3 parsers for one posting
(Phase 4 S2, docs/DECISIONS/0014-pure-posting-composition-and-scoped-d2.md).

`normalize_posting` calls seven of the eight Phase 3 parsers over a
`PostingInputs` value and returns every parser result unchanged. It is the
boundary at which ADR 0011's D2 realistic-output protection is enforced
(`tests/test_normalization_posting_realistic.py`); D2 is satisfied only at
this boundary, and D1 (parser version) is not satisfied by anything here.

Contract:

- **Pure.** No I/O, logging, global state, or import-time loading. The
  skills taxonomy is a required keyword argument, loaded by the caller.
  Equal inputs give equal outputs.
- **Validation before any parser call.** The argument must be a
  `PostingInputs` instance and each of its three fields `str` or `None`;
  otherwise a fixed, categorical `TypeError` is raised whose message never
  contains a runtime value. Each field is read once; the parsers receive
  exactly the values that were validated. `PostingInputs` itself performs
  no normalization (no strip, no case-fold).
- **Fixed call order and wiring**, matching
  `scripts/evaluate_phase3_corpus.py`'s relative order with title first:
  `classify_title(title)`, then `classify_remote_type`,
  `classify_employment_type`, `classify_seniority`, `classify_experience`
  (each `(title, description)`), then `classify_location(location)`, then
  `classify_skills(title, description, taxonomy=taxonomy)`. A parser
  exception propagates immediately; no later parser runs.
- **Pass-through.** `result.inputs is inputs`, and every parser result is
  the identical object the parser returned. Skills are the sole container
  exception: the returned list is copied into a new tuple of the identical
  `SkillMatch` objects, in order. No value or provenance is assigned,
  rewritten, merged, filtered, scored, or reconciled across fields.
  Because results pass through by identity, a result may be a
  parser-owned shared object (for example `classify_location`'s single
  all-unavailable `LocationResult`); callers must never mutate one, even
  through `object.__setattr__`.
- **Salary is excluded.** There is no compensation input, no salary output,
  and no import of `app.normalization.salary` (ADR 0011 L4 stays open).
- **No provider types.** Nothing here sees `DiscoveredJob`, a raw payload,
  or any provider field; mapping provider fields into `PostingInputs` is
  separately authorized later work (S2b). Nothing at runtime calls this
  module yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.normalization.employment import EmploymentType, classify_employment_type
from app.normalization.experience import ExperienceRange, classify_experience
from app.normalization.location import LocationResult, classify_location
from app.normalization.remote import RemoteType, classify_remote_type
from app.normalization.seniority import Seniority, classify_seniority
from app.normalization.skills import SkillMatch, classify_skills
from app.normalization.taxonomy import TaxonomyIndex
from app.normalization.titles import TitleResult, classify_title
from app.normalization.types import NormalizationResult

_ERROR_INPUTS_TYPE = "normalize_posting requires a PostingInputs instance"
_ERROR_FIELD_TYPE = "PostingInputs fields must each be a str or None"


@dataclass(frozen=True)
class PostingInputs:
    """Provider-neutral parser inputs for one posting. `description` is
    plain text; converting provider HTML is never this module's concern.
    There is deliberately no compensation field."""

    title: str | None
    description: str | None
    location: str | None


@dataclass(frozen=True)
class NormalizedPosting:
    """Every composed parser result, unchanged. There is deliberately no
    salary attribute. `title` is smoke-only realistic evidence, never D2
    accuracy evidence (ADR 0014)."""

    inputs: PostingInputs
    title: TitleResult
    remote_type: NormalizationResult[RemoteType]
    employment_type: NormalizationResult[EmploymentType]
    seniority: NormalizationResult[Seniority]
    experience: ExperienceRange
    location: LocationResult
    skills: tuple[SkillMatch, ...]


def _validate(inputs: object) -> tuple[str | None, str | None, str | None]:
    """Reads each field exactly once and returns the values it checked, so
    a parser can never receive a value that was not validated."""
    if not isinstance(inputs, PostingInputs):
        raise TypeError(_ERROR_INPUTS_TYPE)
    values = (inputs.title, inputs.description, inputs.location)
    for value in values:
        if value is not None and not isinstance(value, str):
            raise TypeError(_ERROR_FIELD_TYPE)
    return values


def normalize_posting(inputs: PostingInputs, *, taxonomy: TaxonomyIndex) -> NormalizedPosting:
    """Composes the seven non-salary Phase 3 parsers over `inputs`. See the
    module docstring for the full contract."""
    title, description, location_text = _validate(inputs)

    title_result = classify_title(title)
    remote_type = classify_remote_type(title, description)
    employment_type = classify_employment_type(title, description)
    seniority = classify_seniority(title, description)
    experience = classify_experience(title, description)
    location = classify_location(location_text)
    skills = classify_skills(title, description, taxonomy=taxonomy)

    return NormalizedPosting(
        inputs=inputs,
        title=title_result,
        remote_type=remote_type,
        employment_type=employment_type,
        seniority=seniority,
        experience=experience,
        location=location,
        skills=tuple(skills),
    )
