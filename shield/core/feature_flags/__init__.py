"""shield.core.feature_flags — OpenFeature-compliant feature flag system.

This package requires the [flags] optional extra::

    pip install api-shield[flags]

Importing from this package when the extra is not installed raises an
``ImportError`` with clear installation instructions.

All public symbols are re-exported under Shield-namespaced names.
``openfeature`` never appears in user-facing imports.

Usage
-----
::

    from shield.core.feature_flags import (
        EvaluationContext,
        ShieldFeatureClient,
        EvaluationReason,
        ResolutionDetails,
    )

    ctx = EvaluationContext(key=user_id, attributes={"plan": "pro"})
    value = await flag_client.get_boolean_value("new_checkout", False, ctx)

Custom provider (implements OpenFeature's AbstractProvider)::

    from shield.core.feature_flags import ShieldFlagProvider

    class MyProvider(ShieldFlagProvider):
        ...

Custom hook (implements OpenFeature's Hook interface)::

    from shield.core.feature_flags import ShieldHook
"""

from __future__ import annotations

# ── Guard: raise early with a helpful message if openfeature not installed ──
from shield.core.feature_flags._guard import _require_flags

_require_flags()

# ── OpenFeature ABC re-exports (Shield-namespaced) ──────────────────────────
# These are the extension points for users who want custom providers/hooks.
from openfeature.hook import Hook as ShieldHook
from openfeature.provider import AbstractProvider as ShieldFlagProvider

# ── Client and provider re-exports ──────────────────────────────────────────
# Imported lazily here so the module graph stays clean.
# client.py and provider.py each call _require_flags() themselves.
from shield.core.feature_flags.client import ShieldFeatureClient as ShieldFeatureClient

# ── Hook re-exports ─────────────────────────────────────────────────────────
from shield.core.feature_flags.hooks import (
    AuditHook as AuditHook,
)
from shield.core.feature_flags.hooks import (
    LoggingHook as LoggingHook,
)
from shield.core.feature_flags.hooks import (
    MetricsHook as MetricsHook,
)
from shield.core.feature_flags.hooks import (
    OpenTelemetryHook as OpenTelemetryHook,
)

# ── Shield-native model re-exports ──────────────────────────────────────────
from shield.core.feature_flags.models import (
    EvaluationContext as EvaluationContext,
)
from shield.core.feature_flags.models import (
    EvaluationReason as EvaluationReason,
)
from shield.core.feature_flags.models import (
    FeatureFlag as FeatureFlag,
)
from shield.core.feature_flags.models import (
    FlagStatus as FlagStatus,
)
from shield.core.feature_flags.models import (
    FlagType as FlagType,
)
from shield.core.feature_flags.models import (
    FlagVariation as FlagVariation,
)
from shield.core.feature_flags.models import (
    Operator as Operator,
)
from shield.core.feature_flags.models import (
    Prerequisite as Prerequisite,
)
from shield.core.feature_flags.models import (
    ResolutionDetails as ResolutionDetails,
)
from shield.core.feature_flags.models import (
    RolloutVariation as RolloutVariation,
)
from shield.core.feature_flags.models import (
    RuleClause as RuleClause,
)
from shield.core.feature_flags.models import (
    ScheduledChange as ScheduledChange,
)
from shield.core.feature_flags.models import (
    ScheduledChangeAction as ScheduledChangeAction,
)
from shield.core.feature_flags.models import (
    Segment as Segment,
)
from shield.core.feature_flags.models import (
    SegmentRule as SegmentRule,
)
from shield.core.feature_flags.models import (
    TargetingRule as TargetingRule,
)
from shield.core.feature_flags.provider import (
    ShieldOpenFeatureProvider as ShieldOpenFeatureProvider,
)

__all__ = [
    # Extension points
    "ShieldFlagProvider",
    "ShieldHook",
    # Models
    "EvaluationContext",
    "EvaluationReason",
    "FeatureFlag",
    "FlagStatus",
    "FlagType",
    "FlagVariation",
    "Operator",
    "Prerequisite",
    "ResolutionDetails",
    "RolloutVariation",
    "RuleClause",
    "ScheduledChange",
    "ScheduledChangeAction",
    "Segment",
    "SegmentRule",
    "TargetingRule",
    # Client
    "ShieldFeatureClient",
    # Provider
    "ShieldOpenFeatureProvider",
    # Hooks
    "AuditHook",
    "LoggingHook",
    "MetricsHook",
    "OpenTelemetryHook",
]
