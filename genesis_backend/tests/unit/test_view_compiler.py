import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.domain.mapping.view_compiler import ViewCompiler
from src.infrastructure.database.models.schema_field_mapping import SchemaFieldMapping, FieldCastType
from src.infrastructure.database.models.event import TrackingEvent

@pytest.mark.asyncio
async def test_view_compiler_generates_correct_sql():
    # Arrange
    mock_adapter = MagicMock()
    compiler = ViewCompiler(adapter=mock_adapter)
    
    mock_event = TrackingEvent(id=1, code="user.signup")
    
    mock_mappings = [
        SchemaFieldMapping(
            target_field="user_id",
            source_paths=["$.uid", "$.user.id"],
            cast_type=FieldCastType.STRING
        ),
        SchemaFieldMapping(
            target_field="age",
            source_paths=["$.user_age"],
            cast_type=FieldCastType.INT
        ),
        SchemaFieldMapping(
            target_field="is_active",
            source_paths=["$.active"],
            cast_type=FieldCastType.BOOL
        )
    ]

    async def mock_get_session():
        yield mock_session
        
    mock_session = AsyncMock()
    
    # We have two executes in compile: one for event, one for mappings
    mock_event_result = MagicMock()
    mock_event_result.scalar_one_or_none.return_value = mock_event
    
    mock_mappings_result = MagicMock()
    mock_mappings_result.scalars().all.return_value = mock_mappings
    
    mock_session.execute.side_effect = [mock_event_result, mock_mappings_result]

    with patch('src.domain.mapping.view_compiler.get_async_session', new=mock_get_session, create=True):
        # Act
        sql = await compiler.compile(event_id=1)

    # Assert
    assert "CREATE VIEW v_event_user_signup AS" in sql
    assert "CAST(COALESCE(\n          json_extract(raw_payload, '$.uid'),\n          json_extract(raw_payload, '$.user.id')\n        ) AS TEXT) AS user_id" in sql
    assert "CAST(json_extract(raw_payload, '$.user_age') AS INTEGER) AS age" in sql
    # SQLite boolean cast
    assert "CAST(json_extract(raw_payload, '$.active') AS INTEGER) AS is_active" in sql
    assert "FROM ods_raw_events" in sql
    assert "WHERE json_extract(raw_payload, '$.event') = 'user.signup'" in sql


@pytest.mark.asyncio
async def test_view_compiler_empty_mappings():
    # Arrange
    mock_adapter = MagicMock()
    compiler = ViewCompiler(adapter=mock_adapter)
    
    mock_event = TrackingEvent(id=2, code="empty.event")
    
    async def mock_get_session():
        yield mock_session
        
    mock_session = AsyncMock()
    mock_event_result = MagicMock()
    mock_event_result.scalar_one_or_none.return_value = mock_event
    
    mock_mappings_result = MagicMock()
    mock_mappings_result.scalars().all.return_value = []
    
    mock_session.execute.side_effect = [mock_event_result, mock_mappings_result]

    with patch('src.domain.mapping.view_compiler.get_async_session', new=mock_get_session, create=True):
        # Act
        sql = await compiler.compile(event_id=2)

    # Assert
    assert sql == ""
