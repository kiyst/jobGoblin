"""Location adapter (Workflow v3.2 Slice 2). Imports only the public
`classify_location` entry point -- no private helper, no whole-module
import, no other parser. Serializes the returned `LocationResult`
through its public `city`/`state`/`country`/`postal_code` attributes
(each a `NormalizationResult` with public `value`/`provenance`
attributes) -- no import of `app.normalization.types` is needed for
that, since attribute access alone is sufficient.
"""

from __future__ import annotations

from app.normalization.location import classify_location


def invoke(inputs: dict[str, str | None]) -> dict[str, tuple[object, str]]:
    result = classify_location(inputs["location"])
    return {
        "city": (result.city.value, result.city.provenance.value),
        "state": (result.state.value, result.state.provenance.value),
        "country": (result.country.value, result.country.provenance.value),
        "postal_code": (result.postal_code.value, result.postal_code.provenance.value),
    }
