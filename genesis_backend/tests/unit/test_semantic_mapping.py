import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domain.mapping.service import SemanticMappingService
from src.infrastructure.database.models.event import TrackingEvent

@pytest.mark.asyncio
async def test_propose_mapping_high_confidence():
    # Arrange
    service = SemanticMappingService()
    
    # Mock LLM to return a high confidence json string
    service._call_llm_raw = AsyncMock(return_value='{"matched_field": "user_id", "confidence": 0.95, "reasoning": "Exact match"}')
    
    # Mock properties on event
    mock_event = TrackingEvent(id=1, name="login")
    mock_event.properties = {
        "user_id": {"type": "STRING", "description": "Unique user ID"},
        "client_id": {"type": "STRING", "description": "Device client ID"}
    }
    
    # Act
    result = await service.propose(
        unknown_field="$.uid", 
        event=mock_event, 
        sample_values=["10023", "9901"]
    )
    
    # Assert
    assert result is not None
    assert result.matched_field == "user_id"
    assert result.confidence == 0.95
    assert result.is_high_confidence is True

@pytest.mark.asyncio
async def test_propose_mapping_low_confidence_needs_review():
    # Arrange
    service = SemanticMappingService()
    
    service._call_llm_raw = AsyncMock(return_value='{"matched_field": "session_duration", "confidence": 0.60, "reasoning": "Guess"}')
    
    mock_event = TrackingEvent(id=2, name="video_play")
    mock_event.properties = {
        "session_duration": {"type": "INT"}
    }
    
    # Act
    result = await service.propose(
        unknown_field="$.time", 
        event=mock_event, 
        sample_values=["120"]
    )
    
    # Assert
    assert result is not None
    assert result.matched_field == "session_duration"
    assert result.confidence == 0.60
    assert result.is_high_confidence is False

@pytest.mark.asyncio
async def test_propose_mapping_hallucination_fallback():
    # Arrange
    service = SemanticMappingService()
    
    # Mock LLM to hallucinate a field not in the candidate list
    service._call_llm_raw = AsyncMock(return_value='{"matched_field": "cost_amount_fake", "confidence": 0.99, "reasoning": "Fake"}')
    
    mock_event = TrackingEvent(id=3, name="purchase")
    mock_event.properties = {
        "price": {"type": "FLOAT"}
    }
    
    # Act
    result = await service.propose(
        unknown_field="$.jine", 
        event=mock_event, 
        sample_values=["9.99"]
    )
    
    # Assert
    # Should fallback to UNKNOWN because "cost_amount_fake" is not in the candidate list (price)
    assert result is not None
    assert result.matched_field == "UNKNOWN"
    assert result.confidence == 0.0
    assert result.is_high_confidence is False
