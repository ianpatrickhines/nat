"""
Unit tests for Survey tools.

Tools tested:
- list_surveys
- get_survey
- record_survey_response
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.nat.tools import (
    list_surveys,
    get_survey,
    record_survey_response,
)
from .conftest import (
    run_async,
    create_list_response,
    create_single_response,
    SAMPLE_SURVEY,
)


class TestListSurveys:
    """Tests for list_surveys tool."""

    def test_list_surveys_success(self, patch_get_client: AsyncMock) -> None:
        """Test listing all surveys."""
        patch_get_client.list.return_value = create_list_response(
            "surveys",
            [
                SAMPLE_SURVEY,
                {"id": "survey-2", "name": "Event Feedback"},
            ],
        )

        result = run_async(list_surveys({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 2

    def test_list_surveys_pagination(self, patch_get_client: AsyncMock) -> None:
        """Test listing surveys with pagination."""
        patch_get_client.list.return_value = create_list_response(
            "surveys",
            [SAMPLE_SURVEY],
            total_pages=3,
            current_page=2,
        )

        result = run_async(list_surveys({
            "page_size": 10,
            "page_number": 2,
        }))

        patch_get_client.list.assert_called_once_with(
            "surveys",
            page_size=10,
            page_number=2,
            include=None,
        )

    def test_list_surveys_with_include(self, patch_get_client: AsyncMock) -> None:
        """Test listing surveys with sideloaded questions."""
        patch_get_client.list.return_value = create_list_response(
            "surveys",
            [SAMPLE_SURVEY],
        )

        result = run_async(list_surveys({
            "include": ["survey_questions"],
        }))

        patch_get_client.list.assert_called_once_with(
            "surveys",
            page_size=20,
            page_number=1,
            include=["survey_questions"],
        )

    def test_list_surveys_empty(self, patch_get_client: AsyncMock) -> None:
        """Test listing surveys when none exist."""
        patch_get_client.list.return_value = create_list_response(
            "surveys",
            [],
        )

        result = run_async(list_surveys({}))

        data = json.loads(result["content"][0]["text"])
        assert len(data["data"]) == 0

    def test_list_surveys_error(self, patch_get_client: AsyncMock) -> None:
        """Test listing surveys handles errors."""
        patch_get_client.list.side_effect = Exception("API Error")

        result = run_async(list_surveys({}))

        assert result["is_error"] is True


class TestGetSurvey:
    """Tests for get_survey tool."""

    def test_get_survey_success(self, patch_get_client: AsyncMock) -> None:
        """Test getting a single survey."""
        patch_get_client.get.return_value = create_single_response(
            "surveys",
            SAMPLE_SURVEY,
        )

        result = run_async(get_survey({"id": "survey-1"}))

        data = json.loads(result["content"][0]["text"])
        assert data["data"]["id"] == "survey-1"

    def test_get_survey_with_questions(self, patch_get_client: AsyncMock) -> None:
        """Test getting a survey with questions by default."""
        patch_get_client.get.return_value = create_single_response(
            "surveys",
            SAMPLE_SURVEY,
        )

        result = run_async(get_survey({"id": "survey-1"}))

        # Default include is survey_questions
        patch_get_client.get.assert_called_once_with(
            "surveys",
            "survey-1",
            include=["survey_questions"],
        )

    def test_get_survey_custom_include(self, patch_get_client: AsyncMock) -> None:
        """Test getting a survey with custom include."""
        patch_get_client.get.return_value = create_single_response(
            "surveys",
            SAMPLE_SURVEY,
        )

        result = run_async(get_survey({
            "id": "survey-1",
            "include": ["survey_questions", "survey_question_responses"],
        }))

        patch_get_client.get.assert_called_once_with(
            "surveys",
            "survey-1",
            include=["survey_questions", "survey_question_responses"],
        )

    def test_get_survey_not_found(self, patch_get_client: AsyncMock) -> None:
        """Test getting a non-existent survey."""
        patch_get_client.get.side_effect = Exception("Not Found")

        result = run_async(get_survey({"id": "invalid"}))

        assert result["is_error"] is True


class TestRecordSurveyResponse:
    """Tests for record_survey_response tool."""

    def test_record_response_success(self, patch_get_client: AsyncMock) -> None:
        """Test recording a survey response."""
        patch_get_client.create.return_value = create_single_response(
            "survey_question_responses",
            {
                "id": "response-1",
                "signup_id": "12345",
                "survey_question_id": "question-1",
                "response": "Yes",
            },
        )

        result = run_async(record_survey_response({
            "signup_id": "12345",
            "survey_question_id": "question-1",
            "response": "Yes",
        }))

        data = json.loads(result["content"][0]["text"])
        assert "data" in data

    def test_record_response_text_answer(self, patch_get_client: AsyncMock) -> None:
        """Test recording a text response."""
        patch_get_client.create.return_value = create_single_response(
            "survey_question_responses",
            {
                "id": "response-1",
                "signup_id": "12345",
                "survey_question_id": "question-2",
                "response": "I want to help with phone banking",
            },
        )

        result = run_async(record_survey_response({
            "signup_id": "12345",
            "survey_question_id": "question-2",
            "response": "I want to help with phone banking",
        }))

        call_args = patch_get_client.create.call_args
        assert call_args[0][1]["response"] == "I want to help with phone banking"

    def test_record_response_invalid_signup(self, patch_get_client: AsyncMock) -> None:
        """Test recording response for invalid signup fails."""
        patch_get_client.create.side_effect = Exception("Signup not found")

        result = run_async(record_survey_response({
            "signup_id": "invalid",
            "survey_question_id": "question-1",
            "response": "Yes",
        }))

        assert result["is_error"] is True

    def test_record_response_invalid_question(self, patch_get_client: AsyncMock) -> None:
        """Test recording response for invalid question fails."""
        patch_get_client.create.side_effect = Exception("Question not found")

        result = run_async(record_survey_response({
            "signup_id": "12345",
            "survey_question_id": "invalid",
            "response": "Yes",
        }))

        assert result["is_error"] is True
