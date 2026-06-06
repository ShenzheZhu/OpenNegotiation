"""Compatibility exports for the former OpenNegotiation legacy demo module."""

from opennego.demo import (
    DEMO_BUNDLE_SCHEMA_VERSION,
    DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION,
    LEGACY_MVP_DEMO_BUNDLE_SCHEMA_VERSION,
    LEGACY_MVP_DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION,
    MVP_DEMO_BUNDLE_SCHEMA_VERSION,
    MVP_DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION,
    DemoBundleValidationResult,
    DemoSummary,
    MvpDemoBundleValidationResult,
    MvpDemoSummary,
    run_demo,
    run_mvp_demo,
    validate_demo_bundle,
    validate_mvp_demo_bundle,
)

__all__ = [
    "DEMO_BUNDLE_SCHEMA_VERSION",
    "DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION",
    "LEGACY_MVP_DEMO_BUNDLE_SCHEMA_VERSION",
    "LEGACY_MVP_DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION",
    "MVP_DEMO_BUNDLE_SCHEMA_VERSION",
    "MVP_DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION",
    "DemoBundleValidationResult",
    "DemoSummary",
    "MvpDemoBundleValidationResult",
    "MvpDemoSummary",
    "run_demo",
    "run_mvp_demo",
    "validate_demo_bundle",
    "validate_mvp_demo_bundle",
]
