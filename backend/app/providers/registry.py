from collections.abc import Sequence
from dataclasses import dataclass

from app.providers.base import DiscoveryProvider
from app.schemas.identifiers import is_canonical_slug
from app.schemas.provider import ProviderCapabilities

# Every message below is a fixed, categorical string — never the original
# exception's text, a provider name, or any other runtime value. Same
# non-interpolation convention as `app/discovery/query_planner.py`'s
# `QueryPlanValidationError` messages: none of this data is "trusted" merely
# because it originates from a `DiscoveryProvider`/`ProviderCapabilities`
# object rather than raw input — an adapter can be buggy, and every message
# here must be safe to log or persist verbatim.
_ERROR_INVALID_PROVIDER_SLUG = (
    "a registered provider's name does not match the canonical provider-slug grammar"
)
_ERROR_DUPLICATE_PROVIDER_NAME = "two registered providers share the same name"
_ERROR_CAPABILITIES_RAISED = "a provider's capabilities() call raised or returned a malformed value"
_ERROR_CAPABILITIES_NAME_MISMATCH = (
    "a provider's capabilities().provider does not match its own registered name"
)
_ERROR_NAME_DRIFT = "a registered provider's current name no longer matches its registered name"
_ERROR_UNKNOWN_PROVIDER = "no provider is registered under the requested name"


class ProviderRegistrationError(RuntimeError):
    """Raised only at `ProviderRegistry` construction/resolution time — a
    configuration/wiring problem, never a per-saved-search runtime condition
    (that is `UnknownProviderError`, or the future orchestrator's own
    planning-failure handling). Every raise site is one of:
    - a provider's `.name` failing the canonical lowercase-ASCII-slug
      grammar (`app.schemas.identifiers.is_canonical_slug`);
    - two providers registered under the same name;
    - `provider.capabilities()` raising, or returning a malformed value (its
      declared return type is not runtime-enforced) during registration;
    - `provider.capabilities().provider` not matching the provider's own
      registered `.name`;
    - a previously-registered provider's `.name` having changed since
      registration — detected when the entry is resolved (`get()`), not
      proactively, since a `DiscoveryProvider` is an arbitrary object and is
      never assumed immutable.

    Every message is a fixed, categorical string (see the module-level
    `_ERROR_*` constants) — never the original exception's text, a provider
    name, or any other runtime value.
    """


class UnknownProviderError(RuntimeError):
    """Raised by `ProviderRegistry.get()` for a name with no registered
    provider. The message never contains the requested name."""


@dataclass(frozen=True)
class RegisteredProvider:
    """What `ProviderRegistry.get()` resolves: the provider instance itself,
    plus a read-isolated snapshot of the `ProviderCapabilities` captured at
    registration time. `capabilities` is always a fresh deep copy — neither
    the registry's own stored snapshot nor any other caller's previously
    resolved copy can be mutated through it.
    """

    provider: DiscoveryProvider
    capabilities: ProviderCapabilities


class ProviderRegistry:
    """Holds configured `DiscoveryProvider` instances by name
    (docs/ARCHITECTURE.md §6.4) — the single place the future orchestrator
    asks "which provider is this name, and what does it advertise." Pure
    in-memory: no database access, no network access. No module-level
    singleton — construct one explicitly per composition root/test; there is
    no proven need yet for ambient global access, and a singleton would let
    tests interfere with each other's registration state.

    Registration names are the registry's own authoritative keys, used
    verbatim — a malformed name is rejected outright at construction, never
    silently normalized to fit.
    """

    def __init__(self, providers: Sequence[DiscoveryProvider]) -> None:
        entries: dict[str, RegisteredProvider] = {}
        for provider in providers:
            name = provider.name
            if not is_canonical_slug(name):
                raise ProviderRegistrationError(_ERROR_INVALID_PROVIDER_SLUG)
            if name in entries:
                raise ProviderRegistrationError(_ERROR_DUPLICATE_PROVIDER_NAME)
            try:
                capabilities = provider.capabilities()
                capabilities_provider = capabilities.provider
            except Exception:
                # Covers both `capabilities()` raising outright and a
                # malformed return value (e.g. `None`, or an object with no
                # `.provider` attribute) — a `DiscoveryProvider`'s declared
                # return type is not runtime-enforced, so either failure
                # mode must convert to the same sanitized, categorical
                # exception rather than let a raw `AttributeError` escape.
                raise ProviderRegistrationError(_ERROR_CAPABILITIES_RAISED) from None
            if capabilities_provider != name:
                raise ProviderRegistrationError(_ERROR_CAPABILITIES_NAME_MISMATCH)
            entries[name] = RegisteredProvider(
                provider=provider, capabilities=capabilities.model_copy(deep=True)
            )
        self._entries = entries

    def names(self) -> list[str]:
        """Every registered provider name, alphabetically sorted — a new
        list on every call, never the registry's own internal keys view."""
        return sorted(self._entries.keys())

    def get(self, name: str) -> RegisteredProvider:
        """Resolves `name` to its provider instance and a fresh deep copy of
        its registration-time capabilities snapshot.

        Raises `UnknownProviderError` (message never contains `name`) if
        nothing is registered under it. Raises `ProviderRegistrationError`
        if the provider's own `.name` no longer matches the name it was
        registered under — checked on every resolution, since a
        `DiscoveryProvider` is an arbitrary object and is never assumed
        immutable.
        """
        entry = self._entries.get(name)
        if entry is None:
            raise UnknownProviderError(_ERROR_UNKNOWN_PROVIDER)
        if entry.provider.name != name:
            raise ProviderRegistrationError(_ERROR_NAME_DRIFT)
        return RegisteredProvider(
            provider=entry.provider, capabilities=entry.capabilities.model_copy(deep=True)
        )
