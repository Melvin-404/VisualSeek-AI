import datetime
import uuid
import pytest
import math

from search.query_parser import QueryParser, SearchIntent
from search.reranker import SearchReranker
from search.temporal_search import TemporalSearch


def test_query_parser():
    parser = QueryParser()

    # Test case 1: Person search with attributes
    intent1 = parser.parse("find a man in a red shirt carrying a backpack")
    assert intent1.object_class == "person"
    assert intent1.color == "red"
    assert intent1.gender == "man"
    assert "backpack" in intent1.attributes
    assert "shirt" in intent1.attributes

    # Test case 2: Vehicle search with style
    intent2 = parser.parse("show a yellow suv on camera cam-001 last 2 hours")
    assert intent2.object_class == "car"
    assert intent2.color == "yellow"
    assert intent2.vehicle_style == "SUV"
    assert intent2.time_range_hours == 2.0

    # Test case 3: Cross-camera tracking intent
    intent3 = parser.parse("track the same person across all cameras")
    assert intent3.intent_type == "cross_camera_track"
    assert intent3.object_class == "person"


def test_reranker():
    reranker = SearchReranker()
    intent = SearchIntent(
        object_class="person",
        color="red",
        attributes=["backpack"]
    )

    base_time = 1718000000000.0  # reference epoch ms
    hits = [
        # Match 1: perfect metadata match, high semantic score, recent
        {
            "id": "match-1",
            "class_label": "person",
            "dominant_colour": "red",
            "carried_items": ["backpack"],
            "score": 0.9,
            "timestamp_ms": base_time - 10 * 60 * 1000  # 10 mins ago
        },
        # Match 2: partial metadata match, medium semantic score, older
        {
            "id": "match-2",
            "class_label": "person",
            "dominant_colour": "blue",
            "carried_items": ["backpack"],
            "score": 0.7,
            "timestamp_ms": base_time - 12 * 3600 * 1000  # 12 hours ago
        },
        # Match 3: poor metadata match, low semantic score, very old
        {
            "id": "match-3",
            "class_label": "car",
            "dominant_colour": "blue",
            "carried_items": [],
            "score": 0.4,
            "timestamp_ms": base_time - 48 * 3600 * 1000  # 48 hours ago
        }
    ]

    reranked = reranker.rerank(intent, hits, target_time=base_time, half_life_hours=24.0)
    assert len(reranked) == 3
    assert reranked[0]["id"] == "match-1"
    assert reranked[1]["id"] == "match-2"
    assert reranked[2]["id"] == "match-3"
    
    # Assert rerank_score is properly bounded and descending
    assert reranked[0]["rerank_score"] > reranked[1]["rerank_score"]
    assert reranked[1]["rerank_score"] > reranked[2]["rerank_score"]


# A mock database session for testing temporal queries
class MockSession:
    def __init__(self, query_data):
        self.query_data = query_data

    def query(self, *args):
        return self

    def join(self, *args):
        return self

    def filter(self, *args):
        return self

    def group_by(self, *args):
        return self

    def order_by(self, *args):
        return self

    def distinct(self, *args):
        return self

    def all(self):
        return self.query_data


def test_temporal_search_trajectory():
    # Mock video segment / detection query return values
    # Representing a path cam-01 -> cam-02
    base_date = datetime.datetime(2026, 6, 10, 10, 0, 0)
    
    class MockRow:
        def __init__(self, camera_id, first_seen, last_seen, min_ts, max_ts):
            self.camera_id = camera_id
            self.first_seen = first_seen
            self.last_seen = last_seen
            self.min_ts = min_ts
            self.max_ts = max_ts

    mock_db_results = [
        MockRow("cam-001", base_date, base_date, 1000, 3000),  # Dwell 2s
        MockRow("cam-002", base_date + datetime.timedelta(minutes=5), base_date + datetime.timedelta(minutes=5), 1000, 11000) # Dwell 10s
    ]

    session = MockSession(mock_db_results)
    temporal = TemporalSearch()
    
    path = temporal.get_trajectory_path(session, uuid.uuid4())
    assert len(path) == 2
    assert path[0]["camera_id"] == "cam-001"
    assert path[0]["dwell_time_ms"] == 2000
    assert path[1]["camera_id"] == "cam-002"
    assert path[1]["dwell_time_ms"] == 10000

    dwell_times = temporal.get_camera_dwell_times(session, uuid.uuid4())
    assert dwell_times["cam-001"] == 2000
    assert dwell_times["cam-002"] == 10000


# ─── Additional Query Parser Edge Cases ──────────────────────────────────────

def test_parser_color_only_query():
    """Color-only query should still produce a valid intent."""
    parser = QueryParser()
    intent = parser.parse("red")
    assert intent.color == "red"
    assert intent.object_class is None  # No class context

def test_parser_bare_backpack():
    """A query with *only* 'backpack' (no person context) should treat it as class=backpack, not person."""
    parser = QueryParser()
    intent = parser.parse("backpack near the exit")
    # No person-context words present, so backpack stays as the YOLO class
    assert intent.object_class == "backpack"

def test_parser_backpack_with_person_context():
    """'backpack' with person context should be an attribute, class=person."""
    parser = QueryParser()
    intent = parser.parse("person carrying a backpack")
    assert intent.object_class == "person"
    assert "backpack" in intent.attributes

def test_parser_synonyms():
    """Synonyms like 'vehicle', 'man', 'woman' resolve correctly."""
    parser = QueryParser()
    intent_v = parser.parse("white vehicle parked outside")
    assert intent_v.object_class == "car"
    assert intent_v.color == "white"

    intent_w = parser.parse("woman in blue jacket")
    assert intent_w.object_class == "person"
    assert intent_w.gender == "woman"
    assert intent_w.color == "blue"
    assert "jacket" in intent_w.attributes

def test_parser_time_ranges():
    """Various time range expressions parse correctly."""
    parser = QueryParser()
    assert parser.parse("cars last 5 hours").time_range_hours == 5.0
    assert parser.parse("events past hour").time_range_hours == 1.0
    assert parser.parse("activity today").time_range_hours == 24.0
    assert parser.parse("all trucks").time_range_hours is None

def test_parser_compound_attributes():
    """Compound attributes like 'hard hat' and 'hi-vis' are extracted."""
    parser = QueryParser()
    intent = parser.parse("worker wearing a hard hat and hi-vis vest")
    assert "hard hat" in intent.attributes
    assert "hi-vis vest" in intent.attributes

def test_parser_cross_camera_variants():
    """All cross-camera trigger phrases are detected."""
    parser = QueryParser()
    for phrase in ["same person across cameras", "same car detected", "track the same vehicle"]:
        intent = parser.parse(phrase)
        assert intent.intent_type == "cross_camera_track", f"Failed for: {phrase}"

def test_parser_vehicle_style_inference():
    """Vehicle style alone should infer class=car."""
    parser = QueryParser()
    intent = parser.parse("black sedan")
    assert intent.object_class == "car"
    assert intent.vehicle_style == "SEDAN"
    assert intent.color == "black"


# ─── Additional Reranker Edge Cases ──────────────────────────────────────────

def test_reranker_empty_hits():
    """Reranker should return empty list for empty input."""
    reranker = SearchReranker()
    intent = SearchIntent(object_class="person")
    assert reranker.rerank(intent, []) == []

def test_reranker_single_hit():
    """Reranker should handle single-element input."""
    reranker = SearchReranker()
    intent = SearchIntent(object_class="car", color="red")
    hits = [{"id": "only-1", "class_label": "car", "dominant_colour": "red", "score": 0.8, "timestamp_ms": 1718000000000.0}]
    result = reranker.rerank(intent, hits, target_time=1718000000000.0)
    assert len(result) == 1
    assert result[0]["rerank_score"] > 0.0

def test_reranker_preserves_original_fields():
    """Reranker should not destroy original hit fields."""
    reranker = SearchReranker()
    intent = SearchIntent(object_class="person")
    hits = [{"id": "x", "class_label": "person", "score": 0.5, "timestamp_ms": 1718000000000.0, "custom_field": "preserved"}]
    result = reranker.rerank(intent, hits, target_time=1718000000000.0)
    assert result[0]["custom_field"] == "preserved"

def test_reranker_score_bounds():
    """Combined rerank score should be between 0 and 1."""
    reranker = SearchReranker()
    intent = SearchIntent(object_class="car", color="blue", attributes=["backpack"])
    hits = [
        {"id": "a", "class_label": "car", "dominant_colour": "blue", "carried_items": ["backpack"], "score": 1.0, "timestamp_ms": 1718000000000.0},
        {"id": "b", "class_label": "truck", "dominant_colour": "red", "carried_items": [], "score": 0.0, "timestamp_ms": 0},
    ]
    result = reranker.rerank(intent, hits, target_time=1718000000000.0)
    for r in result:
        assert 0.0 <= r["rerank_score"] <= 1.0, f"Score out of bounds: {r['rerank_score']}"


# ─── Temporal Trajectory Subsequence Test ────────────────────────────────────

def test_temporal_trajectory_subsequence():
    """find_objects_by_trajectory should detect subsequences in camera paths."""
    temporal = TemporalSearch()

    base_date = datetime.datetime(2026, 6, 10, 10, 0, 0)
    g_id = uuid.uuid4()

    class MockRow:
        def __init__(self, camera_id, first_seen, last_seen, min_ts, max_ts):
            self.camera_id = camera_id
            self.first_seen = first_seen
            self.last_seen = last_seen
            self.min_ts = min_ts
            self.max_ts = max_ts

    # Gallery path: cam-A -> cam-B -> cam-C
    trajectory_data = [
        MockRow("cam-A", base_date, base_date, 0, 1000),
        MockRow("cam-B", base_date + datetime.timedelta(minutes=2), base_date + datetime.timedelta(minutes=2), 0, 1000),
        MockRow("cam-C", base_date + datetime.timedelta(minutes=5), base_date + datetime.timedelta(minutes=5), 0, 1000),
    ]

    class MockDistinctSession:
        """Returns a single gallery_id for distinct query, full trajectory for path query."""
        def __init__(self):
            self._mode = "distinct"

        def query(self, *args):
            return self

        def join(self, *args):
            return self

        def filter(self, *args):
            return self

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def distinct(self, *args):
            self._mode = "distinct"
            return self

        def all(self):
            if self._mode == "distinct":
                self._mode = "trajectory"
                return [(g_id,)]
            return trajectory_data

    session = MockDistinctSession()
    # cam-A -> cam-C is a valid subsequence
    matches = temporal.find_objects_by_trajectory(session, ["cam-A", "cam-C"])
    assert len(matches) == 1
    assert matches[0]["gallery_id"] == str(g_id)

