"""Market source policy artifacts for real-market adapter readiness."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json

MARKET_SOURCE_POLICY_SCHEMA_VERSION = "opennego.market_source_policy.v1"
MARKET_SOURCE_VALIDATION_SCHEMA_VERSION = "opennego.market_source_validation.v1"

COLLECTION_MODES = frozenset({"fixture", "offline_export", "official_api", "licensed_dataset"})
LIVE_COLLECTION_MODES = frozenset({"official_api", "licensed_dataset"})
DEFAULT_ALLOWED_FIELDS = (
    "query",
    "title",
    "price",
    "condition",
    "source",
    "currency",
    "sale_mechanism",
    "sold_at",
)
DEFAULT_PROHIBITED_FIELDS = (
    "cookies",
    "raw_html",
    "seller_username",
    "buyer_username",
    "email",
    "phone",
    "address",
    "payment_account",
    "credential",
)


class MarketSourcePolicyError(ValueError):
    """Raised when a market source policy is malformed or unsafe."""


@dataclass(frozen=True)
class MarketSourcePolicy:
    schema_version: str
    source_id: str
    adapter_kind: str
    collection_mode: str
    data_rights: str
    terms_url: str | None
    privacy_classification: str
    allowed_fields: tuple[str, ...]
    prohibited_fields: tuple[str, ...]
    live_collection_enabled: bool
    anti_scraping_policy: str
    credential_policy: str
    retention_policy: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketSourceValidationResult:
    schema_version: str
    status: str
    path: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def generate_market_source_policy(
    *,
    source_id: str,
    adapter_kind: str = "offline_export",
    collection_mode: str = "offline_export",
    data_rights: str = "user_provided_export",
    terms_url: str | None = None,
    privacy_classification: str = "aggregate_or_user_provided_export",
    allowed_fields: Sequence[str] | None = DEFAULT_ALLOWED_FIELDS,
    prohibited_fields: Sequence[str] | None = DEFAULT_PROHIBITED_FIELDS,
    live_collection_enabled: bool = False,
    anti_scraping_policy: str = "no_automated_scraping_without_source_permission",
    credential_policy: str = "no_credentials_in_repo",
    retention_policy: str = "do_not_commit_raw_exports_or_credentials",
    metadata: Mapping[str, Any] | None = None,
) -> MarketSourcePolicy:
    """Generate a provider-neutral source policy for market data adapters."""

    return MarketSourcePolicy(
        schema_version=MARKET_SOURCE_POLICY_SCHEMA_VERSION,
        source_id=_non_empty(source_id, "source_id"),
        adapter_kind=_non_empty(adapter_kind, "adapter_kind"),
        collection_mode=_non_empty(collection_mode, "collection_mode"),
        data_rights=_non_empty(data_rights, "data_rights"),
        terms_url=_optional_non_empty(terms_url, "terms_url"),
        privacy_classification=_non_empty(
            privacy_classification,
            "privacy_classification",
        ),
        allowed_fields=_string_tuple(
            allowed_fields or DEFAULT_ALLOWED_FIELDS,
            "allowed_fields",
        ),
        prohibited_fields=_string_tuple(
            prohibited_fields or DEFAULT_PROHIBITED_FIELDS,
            "prohibited_fields",
        ),
        live_collection_enabled=bool(live_collection_enabled),
        anti_scraping_policy=_non_empty(anti_scraping_policy, "anti_scraping_policy"),
        credential_policy=_non_empty(credential_policy, "credential_policy"),
        retention_policy=_non_empty(retention_policy, "retention_policy"),
        metadata=dict(metadata or {}),
    )


def write_market_source_policy(
    output_path: str | Path,
    *,
    source_id: str,
    adapter_kind: str = "offline_export",
    collection_mode: str = "offline_export",
    data_rights: str = "user_provided_export",
    terms_url: str | None = None,
    privacy_classification: str = "aggregate_or_user_provided_export",
    allowed_fields: Sequence[str] | None = DEFAULT_ALLOWED_FIELDS,
    prohibited_fields: Sequence[str] | None = DEFAULT_PROHIBITED_FIELDS,
    live_collection_enabled: bool = False,
    anti_scraping_policy: str = "no_automated_scraping_without_source_permission",
    credential_policy: str = "no_credentials_in_repo",
    retention_policy: str = "do_not_commit_raw_exports_or_credentials",
    metadata: Mapping[str, Any] | None = None,
) -> MarketSourcePolicy:
    """Write a market source policy artifact and return it."""

    policy = generate_market_source_policy(
        source_id=source_id,
        adapter_kind=adapter_kind,
        collection_mode=collection_mode,
        data_rights=data_rights,
        terms_url=terms_url,
        privacy_classification=privacy_classification,
        allowed_fields=allowed_fields,
        prohibited_fields=prohibited_fields,
        live_collection_enabled=live_collection_enabled,
        anti_scraping_policy=anti_scraping_policy,
        credential_policy=credential_policy,
        retention_policy=retention_policy,
        metadata=metadata,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, policy)
    return policy


def validate_market_source_policy(path: str | Path) -> MarketSourceValidationResult:
    """Validate a market source policy without using live credentials."""

    policy_path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = read_json(policy_path)
    except (OSError, ValueError) as exc:
        return MarketSourceValidationResult(
            schema_version=MARKET_SOURCE_VALIDATION_SCHEMA_VERSION,
            status="failed",
            path=str(policy_path),
            errors=(str(exc),),
            warnings=(),
        )
    _validate_policy_mapping(data, errors, warnings)
    return MarketSourceValidationResult(
        schema_version=MARKET_SOURCE_VALIDATION_SCHEMA_VERSION,
        status="passed" if not errors else "failed",
        path=str(policy_path),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def market_source_policy_summary(path: str | Path) -> Mapping[str, Any]:
    """Return a manifest-safe policy summary or raise on validation failure."""

    policy_path = Path(path)
    validation = validate_market_source_policy(policy_path)
    if validation.status != "passed":
        raise MarketSourcePolicyError(
            f"{policy_path}: invalid market source policy: "
            + "; ".join(validation.errors)
        )
    data = read_json(policy_path)
    return {
        "schema_version": data["schema_version"],
        "path": str(policy_path),
        "sha256": _sha256(policy_path),
        "source_id": data["source_id"],
        "adapter_kind": data["adapter_kind"],
        "collection_mode": data["collection_mode"],
        "data_rights": data["data_rights"],
        "terms_url": data.get("terms_url"),
        "privacy_classification": data["privacy_classification"],
        "live_collection_enabled": data["live_collection_enabled"],
        "anti_scraping_policy": data["anti_scraping_policy"],
        "credential_policy": data["credential_policy"],
        "validation_status": validation.status,
    }


def _validate_policy_mapping(
    data: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    _expect_equal(
        data,
        "schema_version",
        MARKET_SOURCE_POLICY_SCHEMA_VERSION,
        errors,
    )
    _expect_non_empty(data, "source_id", errors)
    _expect_non_empty(data, "adapter_kind", errors)
    mode = _expect_non_empty(data, "collection_mode", errors)
    if mode and mode not in COLLECTION_MODES:
        errors.append(f"collection_mode: unsupported value {mode!r}")
    rights = _expect_non_empty(data, "data_rights", errors)
    terms_url = data.get("terms_url")
    if terms_url is not None and not isinstance(terms_url, str):
        errors.append("terms_url: expected string or null")
    _expect_non_empty(data, "privacy_classification", errors)
    allowed = _expect_string_list(data, "allowed_fields", errors)
    prohibited = _expect_string_list(data, "prohibited_fields", errors)
    overlap = sorted(set(allowed) & set(prohibited))
    if overlap:
        errors.append(f"allowed_fields overlap prohibited_fields: {overlap!r}")
    live_enabled = data.get("live_collection_enabled")
    if not isinstance(live_enabled, bool):
        errors.append("live_collection_enabled: expected boolean")
        live_enabled = False
    anti_scraping = _expect_non_empty(data, "anti_scraping_policy", errors)
    credential_policy = _expect_non_empty(data, "credential_policy", errors)
    _expect_non_empty(data, "retention_policy", errors)
    metadata = data.get("metadata", {})
    if not isinstance(metadata, Mapping):
        errors.append("metadata: expected object")

    if "no_automated_scraping_without_source_permission" not in anti_scraping:
        errors.append(
            "anti_scraping_policy must include "
            "'no_automated_scraping_without_source_permission'"
        )
    if "no_credentials_in_repo" not in credential_policy:
        errors.append("credential_policy must include 'no_credentials_in_repo'")
    if live_enabled:
        if mode not in LIVE_COLLECTION_MODES:
            errors.append(
                "live_collection_enabled requires collection_mode official_api "
                "or licensed_dataset"
            )
        if not isinstance(terms_url, str) or not terms_url.strip():
            errors.append("live_collection_enabled requires terms_url")
        if rights in {"unknown", "user_provided_export"}:
            errors.append(
                "live_collection_enabled requires explicit official or licensed "
                "data_rights"
            )
    elif mode in LIVE_COLLECTION_MODES:
        warnings.append(
            "collection_mode is live-capable but live_collection_enabled is false"
        )


def _expect_equal(
    data: Mapping[str, Any],
    key: str,
    expected: str,
    errors: list[str],
) -> None:
    if data.get(key) != expected:
        errors.append(f"{key}: expected {expected!r}, got {data.get(key)!r}")


def _expect_non_empty(
    data: Mapping[str, Any],
    key: str,
    errors: list[str],
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: expected non-empty string")
        return ""
    return value.strip()


def _expect_string_list(
    data: Mapping[str, Any],
    key: str,
    errors: list[str],
) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        errors.append(f"{key}: expected list")
        return ()
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{key}[{index}]: expected non-empty string")
        else:
            items.append(item.strip())
    return tuple(items)


def _string_tuple(values: Sequence[str], key: str) -> tuple[str, ...]:
    items: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise MarketSourcePolicyError(f"{key}[{index}]: expected non-empty string")
        items.append(value.strip())
    return tuple(items)


def _non_empty(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketSourcePolicyError(f"{key}: expected non-empty string")
    return value.strip()


def _optional_non_empty(value: object, key: str) -> str | None:
    if value is None:
        return None
    return _non_empty(value, key)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
