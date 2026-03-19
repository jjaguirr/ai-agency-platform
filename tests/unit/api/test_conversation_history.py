"""
GET /v1/conversations/{conversation_id}/messages

Returns in-memory history from the EA. Tenant-isolated: a token for
customer A cannot read customer B's history — wrong tenant looks
identical to "conversation not found" (404, not 403 — we don't
disclose that the conversation exists).

History lives on the EA instance. Lost on LRU eviction. That's
acceptable for now; persistent storage is a follow-up.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _token(customer_id: str) -> dict:
    return {"Authorization": f"Bearer {create_token(customer_id)}"}


def _app(registry: EARegistry):
    return create_app(
        ea_registry=registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
    )


def _fake_ea_with_history(customer_id: str, histories: dict):
    """EA mock exposing get_conversation_history()."""
    ea = MagicMock()
    ea.customer_id = customer_id
    ea.get_conversation_history = MagicMock(
        side_effect=lambda cid: histories.get(cid))
    return ea


class TestAuth:
    def test_no_token_401(self):
        registry = EARegistry(factory=lambda cid: MagicMock())
        client = TestClient(_app(registry))
        resp = client.get("/v1/conversations/conv_x/messages")
        assert resp.status_code == 401

    def test_bad_token_401(self):
        registry = EARegistry(factory=lambda cid: MagicMock())
        client = TestClient(_app(registry))
        resp = client.get(
            "/v1/conversations/conv_x/messages",
            headers={"Authorization": "Bearer nonsense"},
        )
        assert resp.status_code == 401


class TestNotFound:
    def test_unknown_conversation_404(self):
        """EA cached, but conversation_id not in its history."""
        ea = _fake_ea_with_history("cust_a", {})
        registry = EARegistry(factory=lambda cid: ea)
        # Seed the cache so peek() finds it
        registry._instances["cust_a"] = ea

        client = TestClient(_app(registry))
        resp = client.get(
            "/v1/conversations/conv_missing/messages",
            headers=_token("cust_a"),
        )
        assert resp.status_code == 404
        assert resp.json()["type"] == "not_found"

    def test_ea_not_cached_404(self):
        """No EA in registry → 404, not a fresh EA build.

        A GET must not trigger EARegistry.get() — that would build an
        EA (Redis + mem0 + LangGraph) just to say "nothing here"."""
        called = []
        registry = EARegistry(factory=lambda cid: called.append(cid) or MagicMock())

        client = TestClient(_app(registry))
        resp = client.get(
            "/v1/conversations/conv_x/messages",
            headers=_token("cust_uncached"),
        )
        assert resp.status_code == 404
        assert called == [], "GET must not instantiate an EA"


class TestTenantIsolation:
    def test_other_customers_conversation_404(self):
        """
        cust_a's token cannot read cust_b's conversation. The route
        scopes by the JWT customer_id — it never looks up cust_b's EA.
        Result: 404, indistinguishable from "doesn't exist".
        """
        ea_a = _fake_ea_with_history("cust_a", {})
        ea_b = _fake_ea_with_history("cust_b", {
            "conv_b1": [
                {"role": "user", "content": "secret", "timestamp": "2026-03-19T00:00:00Z"},
            ],
        })
        registry = EARegistry(factory=lambda cid: {"cust_a": ea_a, "cust_b": ea_b}[cid])
        registry._instances["cust_a"] = ea_a
        registry._instances["cust_b"] = ea_b

        client = TestClient(_app(registry))
        # cust_a tries to read cust_b's conv_b1
        resp = client.get(
            "/v1/conversations/conv_b1/messages",
            headers=_token("cust_a"),
        )
        assert resp.status_code == 404
        # And only cust_a's EA was consulted
        ea_a.get_conversation_history.assert_called_once_with("conv_b1")
        ea_b.get_conversation_history.assert_not_called()


class TestSuccess:
    def test_empty_history_200(self):
        """Conversation exists but has no messages → 200 with []."""
        ea = _fake_ea_with_history("cust_a", {"conv_empty": []})
        registry = EARegistry(factory=lambda cid: ea)
        registry._instances["cust_a"] = ea

        client = TestClient(_app(registry))
        resp = client.get(
            "/v1/conversations/conv_empty/messages",
            headers=_token("cust_a"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["conversation_id"] == "conv_empty"
        assert body["customer_id"] == "cust_a"
        assert body["messages"] == []
        assert body["channel"] is None

    def test_chronological_messages(self):
        ea = _fake_ea_with_history("cust_a", {
            "conv_full": [
                {"role": "user", "content": "hi", "timestamp": "2026-03-19T10:00:00Z", "channel": "chat"},
                {"role": "assistant", "content": "hello", "timestamp": "2026-03-19T10:00:01Z", "channel": "chat"},
                {"role": "user", "content": "thanks", "timestamp": "2026-03-19T10:00:05Z", "channel": "chat"},
                {"role": "assistant", "content": "welcome", "timestamp": "2026-03-19T10:00:06Z", "channel": "chat"},
            ],
        })
        registry = EARegistry(factory=lambda cid: ea)
        registry._instances["cust_a"] = ea

        client = TestClient(_app(registry))
        resp = client.get(
            "/v1/conversations/conv_full/messages",
            headers=_token("cust_a"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert [m["role"] for m in body["messages"]] == \
               ["user", "assistant", "user", "assistant"]
        assert [m["content"] for m in body["messages"]] == \
               ["hi", "hello", "thanks", "welcome"]
        assert body["channel"] == "chat"


class TestRoundtrip:
    """POST a message → GET history → see user + assistant entries.

    Exercises the EA-side history append in handle_customer_interaction.
    """
    def test_post_then_get(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.agents.executive_assistant.ExecutiveAssistantMemory",
                MagicMock,
            )
            mp.setattr(
                "src.agents.executive_assistant.WorkflowCreator",
                MagicMock,
            )
            mp.setattr(
                "src.agents.executive_assistant.ChatOpenAI",
                MagicMock,
            )
            from src.agents.executive_assistant import ExecutiveAssistant

            # Build a real EA, stub its graph + memory to run synchronously.
            ea = ExecutiveAssistant.__new__(ExecutiveAssistant)
            ea.customer_id = "cust_rt"
            ea._history = {}
            from langchain_core.messages import AIMessage

            async def fake_graph_invoke(state):
                state.messages.append(AIMessage(content="reply-from-ea"))
                return state
            ea.graph = MagicMock()
            ea.graph.ainvoke = AsyncMock(side_effect=fake_graph_invoke)
            ea.memory = MagicMock()
            from src.agents.executive_assistant import BusinessContext
            ea.memory.get_business_context = AsyncMock(return_value=BusinessContext())
            ea.memory.get_conversation_context = AsyncMock(return_value={})
            ea.memory.store_conversation_context = AsyncMock()

            registry = EARegistry(factory=lambda cid: ea)
            app = _app(registry)
            client = TestClient(app)

            # POST — creates conversation + appends history
            post = client.post(
                "/v1/conversations/message",
                json={"message": "hello", "channel": "chat",
                      "conversation_id": "conv_rt"},
                headers=_token("cust_rt"),
            )
            assert post.status_code == 200, post.text
            assert post.json()["response"] == "reply-from-ea"

            # GET — history has user + assistant
            get = client.get(
                "/v1/conversations/conv_rt/messages",
                headers=_token("cust_rt"),
            )
            assert get.status_code == 200, get.text
            msgs = get.json()["messages"]
            assert len(msgs) == 2
            assert msgs[0]["role"] == "user"
            assert msgs[0]["content"] == "hello"
            assert msgs[1]["role"] == "assistant"
            assert msgs[1]["content"] == "reply-from-ea"


class TestEARegistryPeek:
    def test_peek_returns_cached(self):
        ea = MagicMock()
        registry = EARegistry(factory=lambda cid: ea)
        registry._instances["cust_x"] = ea
        assert registry.peek("cust_x") is ea

    def test_peek_returns_none_when_absent(self):
        registry = EARegistry(factory=lambda cid: MagicMock())
        assert registry.peek("nope") is None

    def test_peek_does_not_create(self):
        called = []
        registry = EARegistry(factory=lambda cid: called.append(cid))
        registry.peek("nope")
        assert called == []


class TestEAGetConversationHistory:
    """Unit test the EA-side accessor."""
    def test_returns_none_for_unknown(self):
        from unittest.mock import patch
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory"), \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import ExecutiveAssistant
            ea = ExecutiveAssistant(customer_id="cust_hist")
            assert ea.get_conversation_history("never-seen") is None

    def test_returns_list_when_present(self):
        from unittest.mock import patch
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory"), \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import ExecutiveAssistant
            ea = ExecutiveAssistant(customer_id="cust_hist")
            ea._history["conv_1"] = [{"role": "user", "content": "x", "timestamp": "t"}]
            got = ea.get_conversation_history("conv_1")
            assert got == [{"role": "user", "content": "x", "timestamp": "t"}]
