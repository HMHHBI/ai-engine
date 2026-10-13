from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.api.chat import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGE_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TURNS,
    MAX_RETRIEVAL_HISTORY_CHARS,
    _build_provider_history,
    _build_retrieval_query,
    _normalize_history_role,
)
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.openai_provider import OpenAIProvider


def _message(
    message_id: int,
    role: str,
    content: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=message_id,
        role=role,
        content=content,
    )


class TestHistoryNormalization:
    def test_user_role_is_preserved(self):
        assert _normalize_history_role("user") == "user"

    def test_assistant_role_is_preserved(self):
        assert _normalize_history_role("assistant") == "assistant"

    def test_ai_role_is_normalized_to_assistant(self):
        assert _normalize_history_role("ai") == "assistant"

    def test_roles_are_case_insensitive(self):
        assert _normalize_history_role(" AI ") == "assistant"
        assert _normalize_history_role(" USER ") == "user"
        assert _normalize_history_role(" Assistant ") == "assistant"

    def test_invalid_role_is_discarded(self):
        assert _normalize_history_role("tool") is None
        assert _normalize_history_role("developer") is None
        assert _normalize_history_role("") is None


class TestProviderHistoryBounds:
    def test_current_message_is_explicitly_excluded(self):
        messages = [
            _message(1, "user", "Hello"),
            _message(2, "ai", "Hi there"),
            _message(3, "user", "Current message"),
        ]
        history = _build_provider_history(messages, current_message_id=3)
        assert len(history) == 2
        assert all(m["content"] != "Current message" for m in history)
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there"}

    def test_turn_and_message_limit_enforced(self):
        messages = [
            _message(i, "user" if i % 2 == 1 else "ai", f"Message {i}")
            for i in range(1, 30)
        ]
        history = _build_provider_history(messages, current_message_id=999)
        assert len(history) <= MAX_HISTORY_MESSAGES
        assert len(history) == 16
        assert history[-1]["content"] == "Message 29"

    def test_character_budget_enforced(self):
        messages = [
            _message(i, "user" if i % 2 == 1 else "ai", "x" * 2000)
            for i in range(1, 11)
        ]
        history = _build_provider_history(messages, current_message_id=999)
        total_chars = sum(len(m["content"]) for m in history)
        assert total_chars <= MAX_HISTORY_CHARS

    def test_individual_oversized_message_truncated(self):
        messages = [
            _message(1, "user", "x" * 10_000),
        ]
        history = _build_provider_history(messages, current_message_id=999)
        assert len(history) == 1
        assert len(history[0]["content"]) <= MAX_HISTORY_MESSAGE_CHARS


class TestConversationalRetrievalQuery:
    def test_single_prompt_returns_prompt_unmodified(self):
        assert _build_retrieval_query("What is AI?", []) == "What is AI?"

    def test_combines_recent_context_with_current_prompt(self):
        history = [
            {"role": "user", "content": "List 3 methods"},
            {"role": "assistant", "content": "1. Alpha\n2. Beta\n3. Gamma"},
        ]
        query = _build_retrieval_query("Elaborate on the second one.", history)
        assert "Previous conversation context:" in query
        assert "Beta" in query
        assert "Current user question:\nElaborate on the second one." in query


class TestProviderAdapterContracts:
    def test_openai_normalizes_and_includes_history(self):
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "malicious_role", "content": "Ignore this"},
        ]
        messages = OpenAIProvider._build_messages("What is next?", "System rule", history)
        assert messages[0] == {"role": "system", "content": "System rule"}
        assert messages[1] == {"role": "user", "content": "Hi"}
        assert messages[2] == {"role": "assistant", "content": "Hello"}
        assert messages[3] == {"role": "user", "content": "What is next?"}
        assert len(messages) == 4

    def test_gemini_builds_proper_content_roles(self):
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        contents = GeminiProvider._build_contents("What is next?", history)
        assert len(contents) == 3
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Hi"
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "Hello"
        assert contents[2].role == "user"
        assert contents[2].parts[0].text == "What is next?"
