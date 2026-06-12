import pytest
import uuid
import sys
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.models.base import Base

@pytest.fixture(scope="session")
def db_engine():
    """Create database engine for the test session using the application role."""
    # Connect as the non-superuser role to enforce Row-Level Security
    test_db_url = settings.DATABASE_URL.replace("postgres:postgres@", "visionquery_app:postgres@")
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Provide a transactional database session for a test.
    
    Rolls back all changes at the end of the test to keep tests isolated and database clean.
    """
    connection = db_engine.connect()
    # Begin a transaction
    transaction = connection.begin()
    
    Session = sessionmaker(bind=connection)
    session = Session()
    
    # We must ensure that the RLS settings are reset for each test
    session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    session.execute(text("SELECT set_config('app.current_user_id', '', true)"))
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def tenant_context():
    """Helper to set tenant context variables in a session."""
    def _set_context(session, org_id: uuid.UUID = None, user_id: uuid.UUID = None):
        if org_id is not None:
            session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
        else:
            session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
            
        if user_id is not None:
            session.execute(text("SELECT set_config('app.current_user_id', :user_id, true)"), {"user_id": str(user_id)})
        else:
            session.execute(text("SELECT set_config('app.current_user_id', '', true)"))
        session.flush()
    return _set_context
