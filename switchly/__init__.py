"""switchly — route lifecycle management for Python APIs.

All public symbols are available directly from this package::

    from switchly import (
        SwitchlyEngine,
        make_engine,
        MemoryBackend,
        FileBackend,
        RouteState,
        AuditEntry,
        MaintenanceWindow,
        RateLimitPolicy,
        SwitchlyException,
        SlackWebhookFormatter,
        default_formatter,
        # feature flag models (requires switchly[flags])
        FeatureFlag,
        EvaluationContext,
    )

Framework adapters live in their own namespaces::

    from switchly.fastapi import SwitchlyAdmin, SwitchlyMiddleware, SwitchlyRouter, ...
    from switchly.sdk import SwitchlySDK
    from switchly.server import SwitchlyServer
"""

# ---------------------------------------------------------------------------
# Engine & config
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
from switchly.core.backends.base import SwitchlyBackend
from switchly.core.backends.file import FileBackend
from switchly.core.backends.memory import MemoryBackend
from switchly.core.config import make_backend, make_engine
from switchly.core.engine import SwitchlyEngine

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
from switchly.core.exceptions import (
    AmbiguousRouteError,
    EnvGatedException,
    MaintenanceException,
    RateLimitExceededException,
    RouteDisabledException,
    RouteNotFoundException,
    RouteProtectedException,
    SwitchlyException,
    SwitchlyProductionWarning,
)

# ---------------------------------------------------------------------------
# Feature flag models  (pure Pydantic — safe without the [flags] extra)
# ---------------------------------------------------------------------------
from switchly.core.feature_flags.evaluator import FlagEvaluator
from switchly.core.feature_flags.models import (
    EvaluationContext,
    EvaluationReason,
    FeatureFlag,
    FlagStatus,
    FlagType,
    FlagVariation,
    Operator,
    Prerequisite,
    ResolutionDetails,
    RolloutVariation,
    RuleClause,
    Segment,
    SegmentRule,
    TargetingRule,
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
from switchly.core.models import (
    AuditEntry,
    GlobalMaintenanceConfig,
    MaintenanceWindow,
    RouteState,
    RouteStatus,
)

# ---------------------------------------------------------------------------
# Rate limiting models
# ---------------------------------------------------------------------------
from switchly.core.rate_limit.models import (
    GlobalRateLimitPolicy,
    OnMissingKey,
    RateLimitAlgorithm,
    RateLimitHit,
    RateLimitKeyStrategy,
    RateLimitPolicy,
    RateLimitResult,
    RateLimitTier,
)

# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
from switchly.core.webhooks import SlackWebhookFormatter, default_formatter

# ---------------------------------------------------------------------------
# RedisBackend — available only when the [redis] extra is installed
# ---------------------------------------------------------------------------
try:
    from switchly.core.backends.redis import RedisBackend
except ImportError:
    pass

__all__ = [
    # Engine & config
    "SwitchlyEngine",
    "make_engine",
    "make_backend",
    # Backends
    "SwitchlyBackend",
    "MemoryBackend",
    "FileBackend",
    "RedisBackend",
    # Models
    "RouteStatus",
    "RouteState",
    "AuditEntry",
    "MaintenanceWindow",
    "GlobalMaintenanceConfig",
    # Exceptions
    "SwitchlyException",
    "MaintenanceException",
    "EnvGatedException",
    "RouteDisabledException",
    "RouteNotFoundException",
    "AmbiguousRouteError",
    "RouteProtectedException",
    "RateLimitExceededException",
    "SwitchlyProductionWarning",
    # Webhooks
    "default_formatter",
    "SlackWebhookFormatter",
    # Rate limiting
    "RateLimitAlgorithm",
    "OnMissingKey",
    "RateLimitKeyStrategy",
    "RateLimitTier",
    "RateLimitPolicy",
    "RateLimitResult",
    "GlobalRateLimitPolicy",
    "RateLimitHit",
    # Feature flags
    "FlagEvaluator",
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
    "Segment",
    "SegmentRule",
    "TargetingRule",
]
