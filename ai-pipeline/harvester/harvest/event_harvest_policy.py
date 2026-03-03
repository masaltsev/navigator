"""
Business rule: when to run a separate event harvest pass.

See docs/event-harvest-policy.md.

- Yes: source is an event aggregator (afisha, Silver Age events section, etc.).
- No: events were already discovered on the organization page during the normal org crawl.
"""

# Kinds that are event aggregators (run harvest_events as primary or additional pass).
# Core may add e.g. event_aggregator, platform_silverage_events in the future.
EVENT_AGGREGATOR_KINDS: frozenset[str] = frozenset({
    "event_aggregator",
    "platform_silverage_events",
    "afisha",
})


def should_run_event_harvest_separately(
    source_kind: str,
    base_url: str = "",
    *,
    events_already_in_org_run: bool = False,
) -> bool:
    """Decide whether to run a separate event harvest pass for this source.

    Args:
        source_kind: Source kind from Core (org_website, event_aggregator, ...).
        base_url: Reserved for future use (e.g. domain whitelist).
        events_already_in_org_run: If True, events were already discovered and
            imported in the same run as the org crawl → do not run a second pass.

    Returns:
        True if the orchestrator should schedule harvest_events for this source;
        False otherwise.
    """
    if events_already_in_org_run:
        return False

    if source_kind and source_kind.lower() in EVENT_AGGREGATOR_KINDS:
        return True

    return False
