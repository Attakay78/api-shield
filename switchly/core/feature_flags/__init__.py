"""switchly.core.feature_flags — OpenFeature-compliant feature flag system.

This package requires the [flags] optional extra::

    pip install switchly[flags]

Importing from this package when the extra is not installed raises an
``ImportError`` with clear installation instructions.

All public symbols are re-exported under Switchly-namespaced names.
``openfeature`` never appears in user-facing imports.

Usage
-----
::

    from switchly.core.feature_flags import (
        EvaluationContext,
        SwitchlyFeatureClient,
        EvaluationReason,
        ResolutionDetails,
    )

    ctx = EvaluationContext(key=user_id, attributes={"plan": "pro"})
    value = await flag_client.get_boolean_value("new_checkout", False, ctx)

Custom provider (implements OpenFeature's AbstractProvider)::

    from switchly.core.feature_flags import SwitchlyFlagProvider

    class MyProvider(SwitchlyFlagProvider):
        ...

Custom hook (implements OpenFeature's Hook interface)::

    from switchly.core.feature_flags import SwitchlyHook
"""

from __future__ import annotations

# ── Guard: raise early with a helpful message if openfeature not installed ──
from switchly.core.feature_flags._guard import _require_flags

_require_flags()

# ── OpenFeature ABC re-exports (Switchly-namespaced) ──────────────────────────
# These are the extension points for users who want custom providers/hooks.
from openfeature.hook import Hook as SwitchlyHook
from openfeature.provider import AbstractProvider as SwitchlyFlagProvider

# ── Client and provider re-exports ──────────────────────────────────────────
# Imported lazily here so the module graph stays clean.
# client.py and provider.py each call _require_flags() themselves.
from switchly.core.feature_flags.client import SwitchlyFeatureClient as SwitchlyFeatureClient

# ── Hook re-exports ─────────────────────────────────────────────────────────
from switchly.core.feature_flags.hooks import (
    AuditHook as AuditHook,
)
from switchly.core.feature_flags.hooks import (
    LoggingHook as LoggingHook,
)
from switchly.core.feature_flags.hooks import (
    MetricsHook as MetricsHook,
)
from switchly.core.feature_flags.hooks import (
    OpenTelemetryHook as OpenTelemetryHook,
)

# ── Switchly-native model re-exports ──────────────────────────────────────────
from switchly.core.feature_flags.models import (
    EvaluationContext as EvaluationContext,
)
from switchly.core.feature_flags.models import (
    EvaluationReason as EvaluationReason,
)
from switchly.core.feature_flags.models import (
    FeatureFlag as FeatureFlag,
)
from switchly.core.feature_flags.models import (
    FlagStatus as FlagStatus,
)
from switchly.core.feature_flags.models import (
    FlagType as FlagType,
)
from switchly.core.feature_flags.models import (
    FlagVariation as FlagVariation,
)
from switchly.core.feature_flags.models import (
    Operator as Operator,
)
from switchly.core.feature_flags.models import (
    Prerequisite as Prerequisite,
)
from switchly.core.feature_flags.models import (
    ResolutionDetails as ResolutionDetails,
)
from switchly.core.feature_flags.models import (
    RolloutVariation as RolloutVariation,
)
from switchly.core.feature_flags.models import (
    RuleClause as RuleClause,
)
from switchly.core.feature_flags.models import (
    ScheduledChange as ScheduledChange,
)
from switchly.core.feature_flags.models import (
    ScheduledChangeAction as ScheduledChangeAction,
)
from switchly.core.feature_flags.models import (
    Segment as Segment,
)
from switchly.core.feature_flags.models import (
    SegmentRule as SegmentRule,
)
from switchly.core.feature_flags.models import (
    TargetingRule as TargetingRule,
)
from switchly.core.feature_flags.provider import (
    SwitchlyOpenFeatureProvider as SwitchlyOpenFeatureProvider,
)

__all__ = [
    # Extension points
    "SwitchlyFlagProvider",
    "SwitchlyHook",
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
    "SwitchlyFeatureClient",
    # Provider
    "SwitchlyOpenFeatureProvider",
    # Hooks
    "AuditHook",
    "LoggingHook",
    "MetricsHook",
    "OpenTelemetryHook",
]
