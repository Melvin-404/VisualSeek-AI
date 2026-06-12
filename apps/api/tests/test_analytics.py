import uuid
import datetime
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import status
from sqlalchemy import select, func, text

import sys
from unittest.mock import MagicMock

# Prevent Milvus connection and OpenCLIP loading on import
class MockVectorSearchService:
    def __init__(self, *args, **kwargs):
        pass
    async def search(self, *args, **kwargs):
        pass

vector_search_mock_mod = MagicMock()
vector_search_mock_mod.VectorSearchService = MockVectorSearchService
sys.modules["app.services.vector_search"] = vector_search_mock_mod

# Mock spacy to prevent downloading en_core_web_sm
mock_spacy = MagicMock()
mock_nlp = MagicMock()
mock_spacy.load.return_value = mock_nlp
sys.modules["spacy"] = mock_spacy

# Prevent OpenTelemetry connection attempts during tests
sys.modules["opentelemetry"] = None

from app.main import app
from app.models.schema_models import (
    Camera, Event, SearchQuery, DetectedObject, CameraHealthLog, Organization, User
)
from app.services.analytics_service import AnalyticsService
from app.db.session import async_session_maker


@pytest_asyncio.fixture
async def async_db_session():
    """Provide a transactional AsyncSession for test isolation."""
    async with async_session_maker() as session:
        # Reset tenant context variables
        await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
        await session.execute(text("SELECT set_config('app.current_user_id', '', true)"))
        
        yield session
        
        # Roll back transaction to keep database clean
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_test_data(async_db_session):
    """Seed data for analytics testing."""
    # Create Org
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Test Analytics Org")
    async_db_session.add(org)
    
    # Set tenant context asynchronously
    await async_db_session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)}
    )
    await async_db_session.flush()

    # Create User
    user = User(
        org_id=org_id,
        email=f"test.analytics-{uuid.uuid4()}@visionquery.ai",
        hashed_password="hashed_password"
    )
    async_db_session.add(user)
    await async_db_session.flush()

    # Create Camera
    camera = Camera(
        org_id=org_id,
        name="Test Lobby Camera",
        location="lobby",
        rtsp_url="rtsp://admin:pass@lobby-ip/stream",
        status="active"
    )
    async_db_session.add(camera)
    await async_db_session.flush()

    # Create Events (historical and current)
    now = datetime.datetime.now(datetime.timezone.utc)
    event1 = Event(
        id=uuid.uuid4(),
        org_id=org_id,
        camera_id=camera.id,
        event_type="intrusion",
        severity="critical",
        start_time=now - datetime.timedelta(minutes=10),
        end_time=now - datetime.timedelta(minutes=5),
        thumbnail_s3_key="thumb.jpg",
        event_metadata={"source_type": "camera", "confidence_threshold": 0.90, "false_positive": "false"}
    )
    async_db_session.add(event1)

    # Create Search Queries
    sq1 = SearchQuery(
        org_id=org_id,
        user_id=user.id,
        query_text="person in lobby",
        query_embedding=[0.01] * 512,
        results_count=2,
        latency_ms=45,
        created_at=now - datetime.timedelta(days=2) # 2 days ago
    )
    sq_old = SearchQuery(
        org_id=org_id,
        user_id=user.id,
        query_text="old sensitive query",
        query_embedding=[0.01] * 512,
        results_count=5,
        latency_ms=62,
        created_at=now - datetime.timedelta(days=35) # 35 days ago (older than 30 days)
    )
    async_db_session.add_all([sq1, sq_old])
    
    # Create Camera Health Logs
    ch_log = CameraHealthLog(
        id=uuid.uuid4(),
        org_id=org_id,
        camera_id=camera.id,
        timestamp=now - datetime.timedelta(hours=2),
        uptime_status="online",
        frame_drop_rate=1.2,
        detection_latency_ms=145
    )
    async_db_session.add(ch_log)

    # Create Detected Object
    segment_id = uuid.uuid4()
    # Need a video segment to satisfy DetectedObject foreign keys
    from app.models.schema_models import VideoSegment
    segment = VideoSegment(
        id=segment_id,
        org_id=org_id,
        camera_id=camera.id,
        s3_key="segments/test.mp4",
        start_time=now - datetime.timedelta(days=1),
        end_time=now - datetime.timedelta(days=1) + datetime.timedelta(minutes=5),
        duration_ms=300000,
        fps=30,
        resolution="1080p",
        file_size_bytes=50000000,
        processing_status="completed"
    )
    async_db_session.add(segment)
    await async_db_session.flush()

    det = DetectedObject(
        org_id=org_id,
        segment_id=segment.id,
        segment_start_time=segment.start_time,
        frame_number=100,
        timestamp_ms=5000,
        class_label="person",
        confidence=0.92,
        bbox_x=0.2,
        bbox_y=0.4,
        bbox_w=0.1,
        bbox_h=0.3,
        created_at=now - datetime.timedelta(days=1)
    )
    async_db_session.add(det)
    await async_db_session.flush()

    await async_db_session.commit()
    
    # Re-apply tenant context for active transaction
    await async_db_session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)}
    )
    
    yield {"org_id": org_id, "camera_id": camera.id, "user_id": user.id}

    # Cleanup: delete the organization (cascades to users, cameras, events, etc.)
    # Set session_replication_role to replica to disable all triggers/FK checks during cleanup
    await async_db_session.execute(text("SET session_replication_role = 'replica'"))
    await async_db_session.execute(
        text("DELETE FROM organizations WHERE id = :org_id"),
        {"org_id": org_id}
    )
    await async_db_session.commit()
    await async_db_session.execute(text("SET session_replication_role = 'origin'"))
    await async_db_session.commit()


@pytest.mark.asyncio
async def test_kpis_overview_endpoint(seeded_test_data, async_db_session):
    """Verifies that KPIs overview resolves with all correct metric keys."""
    org_id = seeded_test_data["org_id"]
    kpis = await AnalyticsService.get_realtime_kpis(async_db_session, org_id)
    assert "total_cameras" in kpis
    assert "active_cameras" in kpis
    assert "events_per_hour" in kpis
    assert "gpu_utilization_percent" in kpis
    assert kpis["total_cameras"] >= 1


@pytest.mark.asyncio
async def test_traffic_heatmap_format(seeded_test_data, async_db_session):
    """Verifies traffic heatmap yields correct hourly zone grid format."""
    org_id = seeded_test_data["org_id"]
    heatmap = await AnalyticsService.get_traffic_heatmap(async_db_session, org_id)
    assert len(heatmap) == 24
    assert "lobby" in heatmap[0]
    assert "parking_lot_a" in heatmap[0]


@pytest.mark.asyncio
async def test_object_trends_ninety_days(seeded_test_data, async_db_session):
    """Verifies object trends resolves correctly with historical dates."""
    org_id = seeded_test_data["org_id"]
    trends = await AnalyticsService.get_object_trends(async_db_session, org_id)
    assert len(trends) >= 90
    assert "people" in trends[0]
    assert "vehicles" in trends[0]


@pytest.mark.asyncio
async def test_camera_health_matrix(seeded_test_data, async_db_session):
    """Verifies camera fleet health logs and uptime resolution."""
    org_id = seeded_test_data["org_id"]
    health = await AnalyticsService.get_camera_health(async_db_session, org_id)
    assert len(health) >= 1
    assert "uptime_percent" in health[0]
    assert "frame_drop_rate" in health[0]
    assert "latency_ms" in health[0]


@pytest.mark.asyncio
async def test_search_queries_deidentification(seeded_test_data, async_db_session):
    """Asserts that queries older than 30 days are GDPR de-identified (redacted query + user id)."""
    # Run de-identification service method
    rows_updated = await AnalyticsService.deidentify_old_queries(async_db_session)
    assert rows_updated >= 1

    org_id = seeded_test_data["org_id"]

    # Verify that the query older than 35 days was redacted
    stmt_old = select(SearchQuery).where(
        SearchQuery.org_id == org_id,
        SearchQuery.latency_ms == 62
    )
    res_old = await async_db_session.execute(stmt_old)
    sq_old = res_old.scalars().first()
    assert sq_old is not None
    assert sq_old.query_text == "[REDACTED]"
    assert str(sq_old.user_id) == "00000000-0000-0000-0000-000000000000"

    # Verify that the query 2 days ago was NOT redacted
    stmt_new = select(SearchQuery).where(
        SearchQuery.org_id == org_id,
        SearchQuery.latency_ms == 45
    )
    res_new = await async_db_session.execute(stmt_new)
    sq_new = res_new.scalars().first()
    assert sq_new is not None
    assert sq_new.query_text == "person in lobby"
    assert sq_new.user_id == seeded_test_data["user_id"]
