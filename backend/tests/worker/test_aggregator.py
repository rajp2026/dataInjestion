from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from worker.aggregator import _build_aggregate_rows, _trim_tie_events, BATCH_SIZE
from worker.models import AggregateRow


def _make_event(
    event_id: str = "e1",
    tenant_id: str = "t1",
    source: str = "web",
    event_type: str = "click",
    timestamp: datetime = None,
    created_at: datetime = None,
) -> MagicMock:
    """
    Creates a mock Event object for testing without any DB dependency.
    Uses MagicMock so we only set the fields we care about.
    """
    ts = timestamp or datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    ca = created_at or datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    event = MagicMock()
    event.event_id = event_id
    event.tenant_id = tenant_id
    event.source = source
    event.event_type = event_type
    event.timestamp = ts
    event.created_at = ca
    return event


# ─────────────────────────────────────────────
# _build_aggregate_rows() — Core Aggregation
# ─────────────────────────────────────────────

class TestBuildAggregateRows:

    def test_returns_list_of_aggregate_rows(self):
        """Output must be a list of AggregateRow dataclasses, not raw dicts."""
        events = [_make_event()]
        rows = _build_aggregate_rows(events)
        assert all(isinstance(r, AggregateRow) for r in rows)

    def test_single_event_produces_four_dimension_combos_per_bucket(self):
        """
        Every event generates 4 dimension combos × 2 bucket sizes = 8 rows.
        Combos: (source, type), (source, None), (None, type), (None, None)
        """
        events = [_make_event(source="web", event_type="click")]
        rows = _build_aggregate_rows(events)
        assert len(rows) == 8  # 4 combos × 2 bucket sizes (minute + hour)

    def test_uses_none_for_wildcard_dimensions(self):
        """Wildcard rows must use None (not empty string) for source/event_type."""
        events = [_make_event(source="web", event_type="click")]
        rows = _build_aggregate_rows(events)

        sources = {r.source for r in rows}
        event_types = {r.event_type for r in rows}

        assert None in sources        # wildcard source present
        assert None in event_types    # wildcard event_type present
        assert "web" in sources       # specific source present
        assert "click" in event_types # specific type present

    def test_counts_accumulate_for_same_bucket(self):
        """Two events in the same minute bucket must sum to count=2 for the grand total row."""
        ts = datetime(2024, 1, 1, 10, 0, 15, tzinfo=timezone.utc)
        events = [
            _make_event("e1", timestamp=ts),
            _make_event("e2", timestamp=ts),
        ]
        rows = _build_aggregate_rows(events)

        # Grand total row (source=None, event_type=None) for minute bucket
        grand_total = next(
            r for r in rows
            if r.source is None and r.event_type is None and r.bucket_size == "minute"
        )
        assert grand_total.count == 2

    def test_events_in_different_minutes_produce_separate_buckets(self):
        """Events at 10:00 and 10:01 must land in different minute buckets."""
        events = [
            _make_event("e1", timestamp=datetime(2024, 1, 1, 10, 0, 5, tzinfo=timezone.utc)),
            _make_event("e2", timestamp=datetime(2024, 1, 1, 10, 1, 5, tzinfo=timezone.utc)),
        ]
        rows = _build_aggregate_rows(events)

        minute_totals = [
            r for r in rows
            if r.source is None and r.event_type is None and r.bucket_size == "minute"
        ]
        assert len(minute_totals) == 2
        assert all(r.count == 1 for r in minute_totals)

    def test_events_in_same_hour_different_minutes_share_hour_bucket(self):
        """Events at 10:00 and 10:45 must share the same hour bucket."""
        events = [
            _make_event("e1", timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)),
            _make_event("e2", timestamp=datetime(2024, 1, 1, 10, 45, 0, tzinfo=timezone.utc)),
        ]
        rows = _build_aggregate_rows(events)

        hour_totals = [
            r for r in rows
            if r.source is None and r.event_type is None and r.bucket_size == "hour"
        ]
        assert len(hour_totals) == 1
        assert hour_totals[0].count == 2

    def test_different_sources_counted_separately(self):
        """web and mobile events should have separate (source, None) rows."""
        ts = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", source="web",    event_type="click", timestamp=ts),
            _make_event("e2", source="mobile", event_type="click", timestamp=ts),
        ]
        rows = _build_aggregate_rows(events)

        minute_rows = [r for r in rows if r.bucket_size == "minute"]
        web_row = next((r for r in minute_rows if r.source == "web" and r.event_type is None), None)
        mobile_row = next((r for r in minute_rows if r.source == "mobile" and r.event_type is None), None)

        assert web_row is not None and web_row.count == 1
        assert mobile_row is not None and mobile_row.count == 1

    def test_first_seen_and_last_seen_tracked_correctly(self):
        """first_seen should be earliest timestamp, last_seen should be latest."""
        ts_early = datetime(2024, 1, 1, 10, 0, 5, tzinfo=timezone.utc)
        ts_late  = datetime(2024, 1, 1, 10, 0, 50, tzinfo=timezone.utc)
        events = [
            _make_event("e1", timestamp=ts_early),
            _make_event("e2", timestamp=ts_late),
        ]
        rows = _build_aggregate_rows(events)
        grand_total = next(
            r for r in rows
            if r.source is None and r.event_type is None and r.bucket_size == "minute"
        )
        assert grand_total.first_seen == ts_early
        assert grand_total.last_seen == ts_late

    def test_empty_event_list_returns_empty(self):
        """No events → no aggregate rows."""
        assert _build_aggregate_rows([]) == []

    def test_to_db_dict_converts_none_to_empty_string(self):
        """
        AggregateRow.to_db_dict() must convert None → "" for DB storage,
        because PostgreSQL treats NULL != NULL in unique constraints.
        """
        row = AggregateRow(
            tenant_id="t1",
            bucket_start=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            bucket_size="minute",
            source=None,
            event_type=None,
            count=5,
            first_seen=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            last_seen=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        )
        db_dict = row.to_db_dict()
        assert db_dict["source"] == ""
        assert db_dict["event_type"] == ""
