"""
Conversation endpoint: POST /v1/conversations/message

Accepts {message, channel, conversation_id?} → routes through per-customer
EA → returns {response, conversation_id}.

Persistence side effect (this feature): after the EA call, the route
writes both the user message and the assistant reply to
ConversationRepository. The EA stays unaware of Postgres.

The EA already handles specialist failures by falling back to generalist
mode, so a broken specialist must still yield 200. What *should* produce
503 is an EA infrastructure failure (Redis gone mid-request, mem0 down)
where we can't hand back *any* response.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app(ea_instance, *, repo=None, **extra):
    """Build app with a registry that always returns the given EA."""
    registry = EARegistry(factory=lambda cid: ea_instance)
    return create_app(
        ea_registry=registry,
        orchestrator=extra.get("orchestrator") or AsyncMock(),
        whatsapp_manager=extra.get("whatsapp_manager") or MagicMock(),
        redis_client=extra.get("redis_client") or AsyncMock(),
        conversation_repo=repo or AsyncMock(),
    )


@pytest.fixture
def auth_headers():
    tok = create_token("cust_conv")
    return {"Authorization": f"Bearer {tok}"}


class TestConversationHappyPath:
    def test_valid_message_returns_ea_response(self, mock_ea, auth_headers):
        mock_ea.handle_customer_interaction = AsyncMock(
            return_value="Hi, I'm Sarah.")
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "Hi, I'm Sarah."
        assert "conversation_id" in body

    def test_ea_receives_correct_channel_enum(self, mock_ea, auth_headers):
        from src.agents.executive_assistant import ConversationChannel
        app = _app(mock_ea)
        client = TestClient(app)

        client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "whatsapp"},
            headers=auth_headers,
        )

        call_kwargs = mock_ea.handle_customer_interaction.call_args.kwargs
        assert call_kwargs["channel"] == ConversationChannel.WHATSAPP

    def test_conversation_id_roundtrip(self, mock_ea, auth_headers):
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat",
                  "conversation_id": "conv_fixed"},
            headers=auth_headers,
        )

        assert resp.json()["conversation_id"] == "conv_fixed"
        assert mock_ea.handle_customer_interaction.call_args.kwargs[
                   "conversation_id"] == "conv_fixed"

    def test_conversation_id_generated_when_omitted(self, mock_ea, auth_headers):
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.json()["conversation_id"]  # non-empty

    def test_whitespace_conversation_id_normalized(self, mock_ea, auth_headers):
        """
        "   " must not become a Redis key. The schema normalizes
        whitespace-only to None → route generates a fresh UUID.
        """
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat",
                  "conversation_id": "   "},
            headers=auth_headers,
        )

        conv_id = resp.json()["conversation_id"]
        assert conv_id.strip() == conv_id  # no surrounding whitespace
        assert len(conv_id) > 0
        # EA should have received the clean ID, not whitespace
        ea_conv_id = mock_ea.handle_customer_interaction.call_args.kwargs[
            "conversation_id"]
        assert ea_conv_id == conv_id
        assert ea_conv_id.strip() == ea_conv_id


class TestConversationAuth:
    def test_token_customer_id_scopes_ea_lookup(self, mock_ea):
        """
        The EA instance the request is routed to MUST be keyed by the
        customer_id in the token — not by a request body field, not by
        a default. This is the tenant isolation boundary.
        """
        requested_customers: list[str] = []

        def tracking_factory(cid):
            requested_customers.append(cid)
            return mock_ea

        app = create_app(
            ea_registry=EARegistry(factory=tracking_factory),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=AsyncMock(),
            conversation_repo=AsyncMock(),
        )
        client = TestClient(app)
        tok = create_token("cust_from_token")

        client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert requested_customers == ["cust_from_token"]

    def test_no_token_returns_401(self, mock_ea):
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, mock_ea):
        app = _app(mock_ea)
        client = TestClient(app)
        tok = create_token("cust_conv", expires_in=-1)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestConversationValidation:
    def test_invalid_channel_returns_422(self, mock_ea, auth_headers):
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "carrier_pigeon"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, mock_ea, auth_headers):
        app = _app(mock_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"channel": "chat"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestConversationDegradedMode:
    def test_ea_returns_degraded_response_still_200(self, auth_headers):
        """
        EA handles its own specialist failures and returns a fallback
        string. The API should not treat that as an error.
        """
        degraded_ea = AsyncMock()
        degraded_ea.handle_customer_interaction = AsyncMock(
            return_value="I'm having some trouble right now, but here's what I can tell you..."
        )
        app = _app(degraded_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "complex task", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 200

    def test_ea_infra_failure_returns_structured_503(self, auth_headers):
        """
        If the EA itself blows up (not specialist failure — actual
        exception from handle_customer_interaction), caller gets 503
        with a structured body, not a traceback.
        """
        broken_ea = AsyncMock()
        broken_ea.handle_customer_interaction = AsyncMock(
            side_effect=ConnectionError("redis gone"))
        app = _app(broken_ea)
        client = TestClient(app)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 503
        body = resp.json()
        # Exact-match the body shape and detail. Substring blacklists
        # ("Traceback not in", "redis not in") miss novel leaks.
        assert body == {
            "type": "service_unavailable",
            "detail": "Assistant temporarily unavailable.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Persistence side effect — new with this feature
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistence:
    def test_post_creates_conversation_and_appends_two_messages(
            self, mock_ea, auth_headers):
        """
        One POST → conversation upsert + user message + assistant message.
        """
        repo = AsyncMock()
        repo.create_conversation = AsyncMock(return_value="conv_p")
        repo.append_message = AsyncMock(return_value=None)
        mock_ea.handle_customer_interaction = AsyncMock(
            return_value="assistant says hi")
        client = TestClient(_app(mock_ea, repo=repo))

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "user says hi", "channel": "chat",
                  "conversation_id": "conv_p"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        repo.create_conversation.assert_awaited_once()
        create_kw = repo.create_conversation.await_args.kwargs
        assert create_kw["customer_id"] == "cust_conv"
        assert create_kw["conversation_id"] == "conv_p"
        assert create_kw["channel"] == "chat"

        assert repo.append_message.await_count == 2
        calls = repo.append_message.await_args_list
        user_kw = calls[0].kwargs
        asst_kw = calls[1].kwargs

        assert user_kw["role"] == "user"
        assert user_kw["content"] == "user says hi"
        assert user_kw["customer_id"] == "cust_conv"
        assert user_kw["conversation_id"] == "conv_p"

        assert asst_kw["role"] == "assistant"
        assert asst_kw["content"] == "assistant says hi"
        assert asst_kw["customer_id"] == "cust_conv"

    def test_persistence_uses_canonical_role_names(self, mock_ea, auth_headers):
        """
        "user"/"assistant", not LangChain's "human"/"ai". The DB has a
        CHECK constraint enforcing this — make sure the route sends the
        right values.
        """
        repo = AsyncMock()
        client = TestClient(_app(mock_ea, repo=repo))

        client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        roles = [c.kwargs["role"] for c in repo.append_message.await_args_list]
        assert roles == ["user", "assistant"]

    def test_ea_failure_means_no_assistant_message_persisted(
            self, auth_headers):
        """
        If the EA raises, we return 503 and MUST NOT write an assistant
        message. Whether the user message is written is an implementation
        choice (write-ahead vs write-after); what matters is no phantom
        assistant reply.
        """
        repo = AsyncMock()
        broken_ea = AsyncMock()
        broken_ea.handle_customer_interaction = AsyncMock(
            side_effect=ConnectionError("redis gone"))
        client = TestClient(_app(broken_ea, repo=repo))

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )
        assert resp.status_code == 503

        roles = [c.kwargs["role"]
                 for c in repo.append_message.await_args_list]
        assert "assistant" not in roles

    def test_repo_failure_does_not_hide_ea_response(
            self, mock_ea, auth_headers):
        """
        Persistence is a side effect. If Postgres is briefly unavailable
        but the EA responded, the user should still get the reply —
        storage is not on the critical path for a live conversation.

        (The message is lost from history; that's the trade-off. A
        synchronous-only write would mean a Postgres blip takes down
        the whole assistant.)
        """
        repo = AsyncMock()
        repo.create_conversation = AsyncMock(
            side_effect=ConnectionError("pg gone"))
        mock_ea.handle_customer_interaction = AsyncMock(
            return_value="EA still works")
        client = TestClient(_app(mock_ea, repo=repo))

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["response"] == "EA still works"

    def test_roundtrip_through_real_repo_mock(self, mock_ea, auth_headers):
        """
        POST then GET. Storage layer stands in for both routes; asserts
        the conversation_id flows through unchanged and the messages
        the POST wrote are what the GET reads.
        """
        stored: dict[str, list[dict]] = {}

        repo = AsyncMock()

        async def _create(*, customer_id, conversation_id, channel):
            stored.setdefault(conversation_id, [])
            return conversation_id

        async def _append(*, customer_id, conversation_id, role, content, metadata=None):
            stored[conversation_id].append({
                "role": role, "content": content,
                "timestamp": f"2026-03-19T10:00:0{len(stored[conversation_id])}+00:00",
            })

        async def _get(*, customer_id, conversation_id):
            return stored.get(conversation_id)

        repo.create_conversation = AsyncMock(side_effect=_create)
        repo.append_message = AsyncMock(side_effect=_append)
        repo.get_messages = AsyncMock(side_effect=_get)

        mock_ea.handle_customer_interaction = AsyncMock(
            return_value="EA reply")
        client = TestClient(_app(mock_ea, repo=repo))

        # POST
        post_resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat",
                  "conversation_id": "rt_conv"},
            headers=auth_headers,
        )
        assert post_resp.status_code == 200

        # GET
        get_resp = client.get(
            "/v1/conversations/rt_conv/messages",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert len(body["messages"]) == 2
        assert body["messages"][0] == {
            "role": "user", "content": "hello",
            "timestamp": "2026-03-19T10:00:00+00:00",
        }
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][1]["content"] == "EA reply"
