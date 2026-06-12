import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Mock DB engine connection to avoid database hang on startup
import sqlalchemy.ext.asyncio
mock_engine = MagicMock()
mock_conn = AsyncMock()
mock_engine.connect.return_value.__aenter__.return_value = mock_conn
sqlalchemy.ext.asyncio.create_async_engine = MagicMock(return_value=mock_engine)

# Prevent Milvus connection and OpenCLIP loading on import
class MockVectorSearchService:
    def __init__(self, *args, **kwargs):
        pass
    async def search(self, *args, **kwargs):
        pass

vector_search_mock_mod = MagicMock()
vector_search_mock_mod.VectorSearchService = MockVectorSearchService
sys.modules["app.services.vector_search"] = vector_search_mock_mod

from app.main import app
from app.services.nl_query.intent import SearchIntent
from app.db.session import get_db

# Set up a reusable AsyncMock for DB session
mock_db_session = AsyncMock()

async def mock_get_db():
    yield mock_db_session

app.dependency_overrides[get_db] = mock_get_db

client = TestClient(app)


def test_search_unauthorized():
    """Asserts that searching without a valid authentication header returns 401."""
    from app.core.security import get_current_user_payload
    if get_current_user_payload in app.dependency_overrides:
        del app.dependency_overrides[get_current_user_payload]
    response = client.get(
        "/api/v1/search?query=red cars",
        headers={"X-Tenant-ID": "11111111-1111-1111-1111-111111111111"}
    )
    assert response.status_code == 401


def test_search_empty_query():
    """Asserts that passing an empty query string returns a 400 Bad Request."""
    from app.core.security import get_current_user_payload
    mock_user = AsyncMock()
    mock_user.tenant_id = "11111111-1111-1111-1111-111111111111"
    app.dependency_overrides[get_current_user_payload] = lambda: mock_user

    response = client.get(
        "/api/v1/search?query=",
        headers={"X-Tenant-ID": "11111111-1111-1111-1111-111111111111"}
    )
    assert response.status_code == 400
    assert "Search query cannot be empty." in response.json()["detail"]


@pytest.mark.asyncio
async def test_search_endpoint_success():
    """Asserts that a valid query is parsed, searched, and returns a successful response."""
    # 1. Mock user credentials and behavior
    mock_user = AsyncMock()
    mock_user.tenant_id = "11111111-1111-1111-1111-111111111111"
    mock_user.role = "viewer"
    mock_user.sub = "22222222-2222-2222-2222-222222222222"

    mock_intent = SearchIntent(
        intent_type="object_search",
        object_class="car",
        color="red",
        time_range={"start_ms": 1000, "end_ms": 5000, "description": "today"},
        camera_ids=["cam-001"],
        rewritten_query="red car",
        raw_query="red cars on cam-001 today"
    )

    mock_search_results = {
        "results": [
            {
                "id": "match-1",
                "camera_id": "cam-001",
                "timestamp_ms": 2000,
                "score": 0.89,
                "object_classes": ["car"],
                "raw_labels": {"detections": [{"label": "car", "bbox": [0.1, 0.1, 0.3, 0.3]}]}
            }
        ],
        "count": 1,
        "next_cursor": None,
        "cached": False,
        "latency_ms": 12.5
    }

    # 2. Patch dependencies
    from app.core.security import get_current_user_payload
    app.dependency_overrides[get_current_user_payload] = lambda: mock_user

    # Configure the mocked database session execution to return no cameras
    mock_db_session.reset_mock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    with patch("app.api.v1.routers.search.nlu_parser.parse", new_callable=AsyncMock, return_value=mock_intent) as mock_parse, \
         patch("app.api.v1.routers.search.vector_search_service.search", new_callable=AsyncMock, return_value=mock_search_results) as mock_search:

        response = client.get(
            "/api/v1/search?query=red cars on cam-001 today",
            headers={"X-Tenant-ID": "11111111-1111-1111-1111-111111111111"}
        )
        
        # 3. Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "red cars on cam-001 today"
        assert data["intent"]["object_class"] == "car"
        assert data["intent"]["color"] == "red"
        assert data["count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "match-1"
        assert data["results"][0]["camera_id"] == "cam-001"

        # Verify NLU Parser was called correctly
        mock_parse.assert_called_once_with("red cars on cam-001 today")
        
        # Verify Vector Search Service was called with mapped ParsedQuery override
        mock_search.assert_called_once()
        args, kwargs = mock_search.call_args
        assert kwargs["query_text"] == "red cars on cam-001 today"
        assert kwargs["parsed_query_override"].classes == ["car"]
        assert kwargs["parsed_query_override"].start_time == 1000

