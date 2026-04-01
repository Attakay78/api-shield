# Rollouts

A rollout gradually exposes a new feature to a percentage of your users. If something goes wrong, shrink the percentage, fix the issue, and expand again without deploying code.

Rollouts are built on top of feature flags, giving you percentage buckets, individual overrides, segments, and prerequisites.

!!! note "Optional dependency"
    Rollouts require the `flags` extra:
    ```bash
    uv add "waygate[flags]"
    ```

---

## How percentage rollouts work

Each user is hashed into a bucket (0-100,000) based on their `context.key`. The hash is deterministic: the same user always lands in the same bucket and never flips between variations across requests. Weights assigned to variations determine which bucket range each variation owns.

---

## Basic rollout: ship to 10% first

```python
from waygate import FeatureFlag, FlagType, FlagVariation, RolloutVariation

await engine.save_flag(
    FeatureFlag(
        key="new-checkout",
        name="New Checkout Flow",
        type=FlagType.BOOLEAN,
        variations=[
            FlagVariation(name="on",  value=True),
            FlagVariation(name="off", value=False),
        ],
        off_variation="off",
        fallthrough=[
            RolloutVariation(variation="on",  weight=10_000),   # 10%
            RolloutVariation(variation="off", weight=90_000),   # 90%
        ],
    )
)
```

Weights are integers out of 100,000. Evaluate the flag in your route handler:

```python
from waygate import EvaluationContext

@router.get("/checkout")
async def checkout(request: Request):
    ctx = EvaluationContext(key=request.state.user_id)
    use_new = await engine.flag_client.get_boolean_value("new-checkout", False, ctx)

    if use_new:
        return new_checkout_response()
    return legacy_checkout_response()
```

---

## Expanding the rollout

Increase the weight over time. Changes take effect on the next evaluation with no restart.

### Via the engine

```python
# 10% -> 50%
flag = await engine.get_flag("new-checkout")
flag.fallthrough = [
    RolloutVariation(variation="on",  weight=50_000),
    RolloutVariation(variation="off", weight=50_000),
]
await engine.save_flag(flag)
```

### Via the dashboard

Open the **Flags** page, click `new-checkout`, go to the **Variations** tab, and adjust the rollout sliders. The change applies immediately to all connected SDK clients.

### Via the CLI

```bash
waygate flags edit new-checkout
```

---

## Pinning specific users (beta testers)

Use `targets` to guarantee specific users always get a variation, regardless of their bucket. Individual targets are evaluated before percentage buckets.

```python
FeatureFlag(
    key="new-checkout",
    ...
    targets={
        "on":  ["beta_tester_1", "beta_tester_2", "internal_qa"],
        "off": ["opted_out_user"],
    },
)
```

### Via the CLI

```bash
waygate flags target new-checkout --variation on --context-key beta_tester_1
waygate flags untarget new-checkout --context-key beta_tester_1
```

---

## Targeting a segment first

Roll out to a named group before expanding to everyone. Create the segment once and reuse it across flags.

```python
from waygate import Segment

await engine.save_segment(Segment(
    key="beta-users",
    name="Beta Users",
    included=["user_1", "user_2", "user_3"],
))
```

Add a targeting rule that sends beta users to `"on"` and routes everyone else through the percentage fallthrough:

```python
from waygate import TargetingRule, RuleClause, Operator

FeatureFlag(
    key="new-checkout",
    ...
    rules=[
        TargetingRule(
            description="Beta users get the new flow",
            clauses=[
                RuleClause(
                    attribute="key",
                    operator=Operator.IN_SEGMENT,
                    values=["beta-users"],
                )
            ],
            variation="on",
        )
    ],
    fallthrough=[
        RolloutVariation(variation="on",  weight=5_000),   # 5% of everyone else
        RolloutVariation(variation="off", weight=95_000),
    ],
)
```

---

## Full rollout and cleanup

When the feature is stable, set the fallthrough to 100% and remove the old code path:

```python
flag.fallthrough = [
    RolloutVariation(variation="on", weight=100_000),
]
await engine.save_flag(flag)
```

Once all clients have migrated, delete the flag:

```bash
waygate flags delete new-checkout
```

---

## Canary rollout

A canary targets a single stable identifier (an API key, tenant ID, or service name) rather than a percentage of users. Useful for validating behaviour against one production tenant before expanding.

```python
from waygate import TargetingRule, RuleClause, Operator

FeatureFlag(
    key="new-search-index",
    ...
    rules=[
        TargetingRule(
            description="Canary tenant",
            clauses=[
                RuleClause(
                    attribute="key",
                    operator=Operator.IS,
                    values=["tenant_acme"],
                )
            ],
            variation="on",
        )
    ],
    fallthrough=[
        RolloutVariation(variation="off", weight=100_000),
    ],
)
```

---

## Kill switch

Setting `enabled=False` skips all rules and returns `off_variation` to every caller immediately.

```python
flag = await engine.get_flag("new-checkout")
flag.enabled = False
await engine.save_flag(flag)
```

```bash
waygate flags disable new-checkout
```

Re-enable when the issue is resolved:

```bash
waygate flags enable new-checkout
```

---

## Next step

[**Tutorial: Webhooks**](webhooks.md)
