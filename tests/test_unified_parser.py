"""Comprehensive tests for UnifiedResultParser."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from folios_v2.domain import ExecutionTask, Request
from folios_v2.domain.enums import ExecutionMode, LifecycleState, ProviderId, RequestType
from folios_v2.providers import ExecutionTaskContext
from folios_v2.providers.exceptions import ParseError
from folios_v2.providers.unified_parser import UnifiedResultParser

# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "provider_responses"


@pytest.fixture
def temp_artifact_dir(tmp_path: Path) -> Path:
    """Create a temporary artifact directory for testing."""
    artifact_dir = tmp_path / "artifacts" / str(uuid4())
    artifact_dir.mkdir(parents=True)
    return artifact_dir


@pytest.fixture
def mock_request() -> Request:
    """Create a mock Request object for testing."""
    return Request(
        id=uuid4(),
        strategy_id=uuid4(),
        provider_id=ProviderId.GEMINI,
        mode=ExecutionMode.CLI,
        request_type=RequestType.RESEARCH,
        metadata={"strategy_prompt": "Test strategy prompt"},
    )


@pytest.fixture
def mock_task() -> ExecutionTask:
    """Create a mock ExecutionTask object for testing."""
    request_id = uuid4()
    return ExecutionTask(
        id=uuid4(),
        request_id=request_id,
        sequence=1,
        mode=ExecutionMode.CLI,
        lifecycle_state=LifecycleState.SUCCEEDED,
    )


@pytest.fixture
def execution_context(
    mock_request: Request, mock_task: ExecutionTask, temp_artifact_dir: Path
) -> ExecutionTaskContext:
    """Create an ExecutionTaskContext for testing."""
    return ExecutionTaskContext(
        request=mock_request,
        task=mock_task,
        artifact_dir=temp_artifact_dir,
        config={},
    )


class TestCliStructuredParsing:
    """Tests for parsing CLI structured.json outputs."""

    @pytest.mark.asyncio
    async def test_parse_structured_json_success(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test successful parsing of structured.json file."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test_provider")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["provider"] == "test_provider"
        assert result["source"] == "cli_structured"
        assert "recommendations" in result
        assert len(result["recommendations"]) == 2

        # Check BUY recommendation
        buy_rec = result["recommendations"][0]
        assert buy_rec["ticker"] == "NVDA"
        assert buy_rec["company_name"] == "NVIDIA Corporation"
        assert buy_rec["action"] == "BUY"
        assert buy_rec["current_price"] == 155.25
        assert buy_rec["target_price"] == 185.00
        assert buy_rec["confidence"] == 85
        assert "investment_thesis" in buy_rec
        assert "key_metrics" in buy_rec

        # Check SELL recommendation
        sell_rec = result["recommendations"][1]
        assert sell_rec["ticker"] == "AAPL"
        assert sell_rec["action"] == "SELL"
        assert sell_rec["confidence"] == 75

    @pytest.mark.asyncio
    async def test_parse_structured_json_with_no_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing structured.json with empty recommendations array."""
        # Setup
        fixture_path = FIXTURES_DIR / "no_recommendations.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("gemini")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["recommendations"] == []
        assert result["overall_sentiment"] == "neutral"
        assert "market_context" in result

    @pytest.mark.asyncio
    async def test_parse_structured_json_malformed(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing malformed structured.json raises ParseError."""
        # Setup
        fixture_path = FIXTURES_DIR / "malformed_json.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test_provider")

        # Execute & Assert
        with pytest.raises(ParseError, match="Malformed JSON"):
            await parser.parse(execution_context)

    @pytest.mark.asyncio
    async def test_parse_structured_json_not_dict(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing structured.json that's not a dict raises ParseError."""
        # Setup
        target_path = execution_context.artifact_dir / "structured.json"
        target_path.write_text('["array", "not", "dict"]')

        parser = UnifiedResultParser("test_provider")

        # Execute & Assert
        with pytest.raises(ParseError, match="Expected dict"):
            await parser.parse(execution_context)


class TestCliResponseParsing:
    """Tests for parsing CLI response.json outputs."""

    @pytest.mark.asyncio
    async def test_parse_response_with_structured_field(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing response.json with embedded structured field."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_response_with_structured.json"
        target_path = execution_context.artifact_dir / "response.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("gemini")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "cli_response_structured"
        assert result["provider"] == "gemini"
        assert "recommendations" in result
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "JNJ"
        assert result["recommendations"][0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_parse_response_raw_with_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing response.json with top-level recommendations field."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_response_raw.json"
        target_path = execution_context.artifact_dir / "response.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("openai")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "cli_response_raw"
        assert "recommendations" in result
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "MSFT"
        assert "raw_data" in result

    @pytest.mark.asyncio
    async def test_parse_response_json_malformed(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing malformed response.json raises ParseError."""
        # Setup
        target_path = execution_context.artifact_dir / "response.json"
        target_path.write_text('{"incomplete": ')

        parser = UnifiedResultParser("test_provider")

        # Execute & Assert
        with pytest.raises(ParseError, match="Malformed JSON"):
            await parser.parse(execution_context)

    @pytest.mark.asyncio
    async def test_parse_response_empty(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing empty response.json."""
        # Setup
        fixture_path = FIXTURES_DIR / "empty_response.json"
        target_path = execution_context.artifact_dir / "response.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test_provider")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "cli_response_raw"
        assert result["recommendations"] == []

    @pytest.mark.asyncio
    async def test_parse_response_not_dict(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing response.json that's not a dict raises ParseError."""
        # Setup
        target_path = execution_context.artifact_dir / "response.json"
        target_path.write_text('["array", "not", "dict"]')

        parser = UnifiedResultParser("test_provider")

        # Execute & Assert
        with pytest.raises(ParseError, match="Expected dict"):
            await parser.parse(execution_context)


class TestBatchParsing:
    """Tests for parsing batch JSONL outputs."""

    @pytest.mark.asyncio
    async def test_parse_openai_batch_results(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing OpenAI batch results JSONL file."""
        # Setup
        fixture_path = FIXTURES_DIR / "openai_batch_results.jsonl"
        target_path = execution_context.artifact_dir / "openai_batch_results.jsonl"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("openai")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "batch_jsonl"
        assert result["provider"] == "openai"
        assert result["total"] == 2
        assert "records" in result
        assert len(result["records"]) == 2

        # Verify recommendations were extracted
        assert "recommendations" in result
        tickers = {rec["ticker"] for rec in result["recommendations"]}
        assert tickers == {"GOOGL", "JPM"}

    @pytest.mark.asyncio
    async def test_parse_gemini_batch_results(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing Gemini batch results JSONL file."""
        # Setup
        fixture_path = FIXTURES_DIR / "gemini_batch_results.jsonl"
        target_path = execution_context.artifact_dir / "gemini_batch_results.jsonl"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("gemini")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "batch_jsonl"
        assert result["provider"] == "gemini"
        assert result["total"] == 1
        assert len(result["records"]) == 1
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "TSM"

    @pytest.mark.asyncio
    async def test_parse_openai_batch_with_properties_wrapper(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Ensure recommendations inside properties object are extracted."""
        target_path = execution_context.artifact_dir / "openai_batch_results.jsonl"
        structured_payload = {
            "type": "object",
            "properties": {
                "recommendations": [
                    {
                        "ticker": "TSLA",
                        "action": "SELL_SHORT",
                        "confidence": 70,
                    },
                    {
                        "ticker": "MSFT",
                        "action": "BUY",
                        "confidence": 90,
                    },
                ]
            },
        }
        record = {
            "response": {
                "body": {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(structured_payload)
                            }
                        }
                    ]
                }
            }
        }
        target_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        parser = UnifiedResultParser("openai")
        result = await parser.parse(execution_context)

        assert len(result["recommendations"]) == 2
        tickers = {rec["ticker"] for rec in result["recommendations"]}
        assert tickers == {"TSLA", "MSFT"}

    @pytest.mark.asyncio
    async def test_parse_gemini_batch_with_split_parts(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Ensure concatenated Gemini parts strings are parsed."""
        target_path = execution_context.artifact_dir / "gemini_batch_results.jsonl"
        full_text = json.dumps(
            {
                "recommendations": [
                    {
                        "ticker": "SHOP",
                        "action": "BUY",
                        "confidence": 78,
                    }
                ]
            }
        )
        midpoint = len(full_text) // 2
        parts = [
            {"text": full_text[:midpoint]},
            {"text": full_text[midpoint:]},
        ]
        record = {
            "response": {
                "body": {
                    "candidates": [
                        {
                            "content": {
                                "parts": parts,
                            }
                        }
                    ]
                }
            }
        }
        target_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        parser = UnifiedResultParser("gemini")
        result = await parser.parse(execution_context)

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "SHOP"

    @pytest.mark.asyncio
    async def test_parse_batch_jsonl_with_direct_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch JSONL where recommendations are in each record."""
        # Setup - Create a batch file with direct recommendations
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_data = [
            {
                "recommendations": [
                    {
                        "ticker": "AAPL",
                        "action": "BUY",
                        "confidence": 85,
                        "investment_thesis": "Strong fundamentals",
                    }
                ]
            },
            {
                "recommendations": [
                    {
                        "ticker": "GOOGL",
                        "action": "SELL",
                        "confidence": 75,
                        "investment_thesis": "Overvalued",
                    }
                ]
            },
        ]
        with target_path.open("w") as f:
            for record in batch_data:
                f.write(json.dumps(record) + "\n")

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["total"] == 2
        assert len(result["recommendations"]) == 2
        assert result["recommendations"][0]["ticker"] == "AAPL"
        assert result["recommendations"][1]["ticker"] == "GOOGL"

    @pytest.mark.asyncio
    async def test_parse_batch_jsonl_malformed_line(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch JSONL with malformed line raises ParseError."""
        # Setup
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        target_path.write_text('{"valid": "json"}\n{invalid json}\n')

        parser = UnifiedResultParser("test")

        # Execute & Assert
        with pytest.raises(ParseError, match="Malformed JSON in batch"):
            await parser.parse(execution_context)

    @pytest.mark.asyncio
    async def test_parse_batch_jsonl_empty_lines(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch JSONL with empty lines (should be skipped)."""
        # Setup
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        target_path.write_text('{"recommendations": []}\n\n\n{"recommendations": []}\n')

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - empty lines should be skipped
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_parse_batch_with_response_text_field(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch JSONL with recommendations in response.text field."""
        # Setup - Create batch format with response.text containing JSON
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_record = {
            "response": {
                "text": json.dumps({
                    "recommendations": [
                        {
                            "ticker": "TSLA",
                            "action": "BUY",
                            "confidence": 88,
                            "investment_thesis": "EV leader with strong growth",
                        }
                    ]
                })
            }
        }
        target_path.write_text(json.dumps(batch_record) + "\n")

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["total"] == 1
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "TSLA"

    @pytest.mark.asyncio
    async def test_parse_batch_with_malformed_response_text(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch with malformed JSON in response.text (should be skipped)."""
        # Setup
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_record = {
            "response": {
                "text": "not valid JSON {incomplete"
            }
        }
        target_path.write_text(json.dumps(batch_record) + "\n")

        parser = UnifiedResultParser("test")

        # Execute - should not raise error, just skip malformed text
        result = await parser.parse(execution_context)

        # Assert - no recommendations extracted
        assert result["total"] == 1
        assert len(result["recommendations"]) == 0

    @pytest.mark.asyncio
    async def test_parse_batch_with_response_not_dict(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing batch where response field is not a dict."""
        # Setup
        target_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_record = {
            "response": "string response, not a dict"
        }
        target_path.write_text(json.dumps(batch_record) + "\n")

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - should handle gracefully
        assert result["total"] == 1
        assert len(result["recommendations"]) == 0


class TestParserPriority:
    """Tests for parser file priority (structured.json > response.json > batch)."""

    @pytest.mark.asyncio
    async def test_structured_json_takes_priority_over_response(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that structured.json is parsed when both files exist."""
        # Setup - create both files
        structured_data = {"recommendations": [{"ticker": "STRUCTURED"}]}
        response_data = {"recommendations": [{"ticker": "RESPONSE"}]}

        structured_path = execution_context.artifact_dir / "structured.json"
        response_path = execution_context.artifact_dir / "response.json"

        structured_path.write_text(json.dumps(structured_data))
        response_path.write_text(json.dumps(response_data))

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - structured.json should be used
        assert result["source"] == "cli_structured"
        assert result["recommendations"][0]["ticker"] == "STRUCTURED"

    @pytest.mark.asyncio
    async def test_response_json_takes_priority_over_batch(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that response.json is parsed when both response and batch exist."""
        # Setup
        response_data = {"recommendations": [{"ticker": "RESPONSE"}]}
        response_path = execution_context.artifact_dir / "response.json"
        response_path.write_text(json.dumps(response_data))

        batch_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_path.write_text('{"recommendations": [{"ticker": "BATCH"}]}\n')

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - response.json should be used
        assert result["source"] == "cli_response_raw"
        assert result["recommendations"][0]["ticker"] == "RESPONSE"

    @pytest.mark.asyncio
    async def test_batch_used_when_no_cli_outputs(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that batch file is parsed when no CLI outputs exist."""
        # Setup - only create batch file
        batch_path = execution_context.artifact_dir / "test_batch_results.jsonl"
        batch_path.write_text('{"recommendations": [{"ticker": "BATCH"}]}\n')

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["source"] == "batch_jsonl"
        assert result["recommendations"][0]["ticker"] == "BATCH"


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_no_parseable_files_raises_error(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that ParseError is raised when no parseable files exist."""
        # Setup - empty artifact directory
        parser = UnifiedResultParser("test")

        # Execute & Assert
        with pytest.raises(ParseError, match="No parseable results found"):
            await parser.parse(execution_context)

    @pytest.mark.asyncio
    async def test_error_message_lists_available_files(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that error message lists available files in directory."""
        # Setup - create some non-parseable files
        (execution_context.artifact_dir / "prompt.txt").write_text("test prompt")
        (execution_context.artifact_dir / "stderr.log").write_text("test stderr")

        parser = UnifiedResultParser("test")

        # Execute & Assert
        with pytest.raises(ParseError) as exc_info:
            await parser.parse(execution_context)

        assert "Available files:" in str(exc_info.value)
        assert "prompt.txt" in str(exc_info.value)
        assert "stderr.log" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_preserves_context_metadata(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that parsed results include context metadata."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test_provider")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - context metadata should be included
        assert result["provider"] == "test_provider"
        assert result["request_id"] == str(execution_context.request.id)
        assert result["task_id"] == str(execution_context.task.id)
        assert result["strategy_id"] == str(execution_context.request.strategy_id)
        assert result["prompt"] == "Test strategy prompt"


class TestRecommendationExtraction:
    """Tests for extracting specific recommendation data."""

    @pytest.mark.asyncio
    async def test_extract_buy_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test extracting BUY action recommendations."""
        # Setup
        fixture_path = FIXTURES_DIR / "mixed_actions.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        buy_recs = [r for r in result["recommendations"] if r["action"] == "BUY"]
        assert len(buy_recs) == 2
        assert buy_recs[0]["ticker"] == "AMD"
        assert buy_recs[1]["ticker"] == "QCOM"

    @pytest.mark.asyncio
    async def test_extract_sell_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test extracting SELL action recommendations."""
        # Setup
        fixture_path = FIXTURES_DIR / "mixed_actions.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        sell_recs = [r for r in result["recommendations"] if r["action"] == "SELL"]
        assert len(sell_recs) == 1
        assert sell_recs[0]["ticker"] == "INTC"

    @pytest.mark.asyncio
    async def test_extract_hold_recommendations(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test extracting HOLD action recommendations."""
        # Setup
        fixture_path = FIXTURES_DIR / "mixed_actions.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        hold_recs = [r for r in result["recommendations"] if r["action"] == "HOLD"]
        assert len(hold_recs) == 1
        assert hold_recs[0]["ticker"] == "MU"

    @pytest.mark.asyncio
    async def test_extract_multiple_recommendations_from_single_response(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test extracting multiple buy/sell actions from single response."""
        # Setup
        fixture_path = FIXTURES_DIR / "mixed_actions.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert len(result["recommendations"]) == 4
        assert result["overall_sentiment"] == "neutral"
        assert "market_context" in result


class TestDataValidation:
    """Tests for validating extracted data fields."""

    @pytest.mark.asyncio
    async def test_ticker_symbols_extracted_correctly(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that ticker symbols are correctly extracted."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        tickers = [r["ticker"] for r in result["recommendations"]]
        assert "NVDA" in tickers
        assert "AAPL" in tickers
        assert all(isinstance(t, str) for t in tickers)

    @pytest.mark.asyncio
    async def test_actions_extracted_correctly(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that action values are correctly extracted."""
        # Setup
        fixture_path = FIXTURES_DIR / "mixed_actions.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        actions = [r["action"] for r in result["recommendations"]]
        assert "BUY" in actions
        assert "SELL" in actions
        assert "HOLD" in actions
        assert all(a in ["BUY", "SELL", "HOLD", "SELL_SHORT"] for a in actions)

    @pytest.mark.asyncio
    async def test_confidence_values_extracted(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that confidence values are correctly extracted."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        confidences = [r["confidence"] for r in result["recommendations"]]
        assert all(isinstance(c, int) for c in confidences)
        assert all(0 <= c <= 100 for c in confidences)

    @pytest.mark.asyncio
    async def test_investment_thesis_extracted(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that investment thesis text is extracted."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        for rec in result["recommendations"]:
            assert "investment_thesis" in rec
            assert isinstance(rec["investment_thesis"], str)
            assert len(rec["investment_thesis"]) > 0

    @pytest.mark.asyncio
    async def test_optional_fields_extracted_when_present(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test that optional fields are extracted when present."""
        # Setup
        fixture_path = FIXTURES_DIR / "cli_structured.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        first_rec = result["recommendations"][0]
        assert "key_metrics" in first_rec
        assert "risk_factors" in first_rec
        assert "catalysts" in first_rec
        assert isinstance(first_rec["risk_factors"], list)
        assert isinstance(first_rec["catalysts"], list)


class TestProviderSpecificBehavior:
    """Tests for provider-specific parsing behavior."""

    @pytest.mark.asyncio
    async def test_gemini_json_block_extraction(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing Gemini responses with JSON in markdown blocks."""
        # Setup
        fixture_path = FIXTURES_DIR / "gemini_with_json_block.json"
        target_path = execution_context.artifact_dir / "response.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("gemini")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert "recommendations" in result
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "SMCI"
        assert result["recommendations"][0]["action"] == "SELL"

    @pytest.mark.asyncio
    async def test_openai_format_with_message_content(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test parsing OpenAI batch format with message content."""
        # Setup
        fixture_path = FIXTURES_DIR / "openai_batch_results.jsonl"
        target_path = execution_context.artifact_dir / "openai_batch_results.jsonl"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("openai")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["provider"] == "openai"
        assert result["source"] == "batch_jsonl"
        assert "records" in result


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    @pytest.mark.asyncio
    async def test_empty_recommendations_array(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test handling empty recommendations array."""
        # Setup
        fixture_path = FIXTURES_DIR / "no_recommendations.json"
        target_path = execution_context.artifact_dir / "structured.json"
        shutil.copy(fixture_path, target_path)

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert result["recommendations"] == []
        assert "analysis_summary" in result

    @pytest.mark.asyncio
    async def test_null_values_in_optional_fields(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test handling null values in optional fields."""
        # Setup
        data = {
            "recommendations": [
                {
                    "ticker": "TEST",
                    "company_name": "Test Corp",
                    "action": "BUY",
                    "confidence": 80,
                    "investment_thesis": "Test thesis",
                    "current_price": None,
                    "target_price": None,
                    "key_metrics": None,
                }
            ]
        }
        target_path = execution_context.artifact_dir / "structured.json"
        target_path.write_text(json.dumps(data))

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert - should handle null values gracefully
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["ticker"] == "TEST"

    @pytest.mark.asyncio
    async def test_unicode_in_text_fields(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test handling Unicode characters in text fields."""
        # Setup
        data = {
            "recommendations": [
                {
                    "ticker": "SAP",
                    "company_name": "SAP SE",
                    "action": "BUY",
                    "confidence": 75,
                    "investment_thesis": "European tech leader € £ ¥ with global reach",
                }
            ]
        }
        target_path = execution_context.artifact_dir / "structured.json"
        target_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert "€" in result["recommendations"][0]["investment_thesis"]

    @pytest.mark.asyncio
    async def test_very_large_recommendations_array(
        self, execution_context: ExecutionTaskContext
    ) -> None:
        """Test handling large recommendations arrays."""
        # Setup - create 50 recommendations
        recommendations = [
            {
                "ticker": f"TKR{i:02d}",
                "company_name": f"Company {i}",
                "action": "BUY" if i % 2 == 0 else "SELL",
                "confidence": 70 + (i % 30),
                "investment_thesis": f"Investment thesis for company {i}",
            }
            for i in range(50)
        ]
        data = {"recommendations": recommendations}
        target_path = execution_context.artifact_dir / "structured.json"
        target_path.write_text(json.dumps(data))

        parser = UnifiedResultParser("test")

        # Execute
        result = await parser.parse(execution_context)

        # Assert
        assert len(result["recommendations"]) == 50
