"""Message store protocol and in-memory default implementation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .provider import MessageStatus, SendResult, IncomingMessage


@dataclass
class MessageRecord:
    provider_message_id: str
    conversation_id: str
    customer_id: str
    direction: str          # "inbound" | "outbound"
    body: str
    counterparty: str       # E.164 phone number of the other party
    timestamp: datetime = field(default_factory=datetime.now)


class MessageStore(Protocol):
    async def record_outbound(self, customer_id: str, conversation_id: str,
                              result: SendResult, to: str, body: str) -> None: ...

    async def record_inbound(self, customer_id: str, conversation_id: str,
                             msg: IncomingMessage) -> None: ...

    async def update_status(self, provider_message_id: str,
                            status: MessageStatus) -> None: ...

    async def get_status(self, provider_message_id: str) -> MessageStatus | None: ...


class InMemoryMessageStore:
    """
    Default message store. Zero external dependencies.
    Unbounded in-memory — production should inject a DB-backed implementation.
    """

    def __init__(self) -> None:
        self._status: dict[str, MessageStatus] = {}
        self._log: dict[str, list[MessageRecord]] = {}

    async def record_outbound(self, customer_id: str, conversation_id: str,
                              result: SendResult, to: str, body: str) -> None:
        self._status[result.provider_message_id] = result.status
        self._log.setdefault(conversation_id, []).append(MessageRecord(
            provider_message_id=result.provider_message_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            direction="outbound",
            body=body,
            counterparty=to,
        ))

    async def record_inbound(self, customer_id: str, conversation_id: str,
                             msg: IncomingMessage) -> None:
        self._log.setdefault(conversation_id, []).append(MessageRecord(
            provider_message_id=msg.provider_message_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            direction="inbound",
            body=msg.body,
            counterparty=msg.from_number,
        ))

    async def update_status(self, provider_message_id: str,
                            status: MessageStatus) -> None:
        self._status[provider_message_id] = status

    async def get_status(self, provider_message_id: str) -> MessageStatus | None:
        return self._status.get(provider_message_id)

    def get_conversation_log(self, conversation_id: str) -> list[MessageRecord]:
        """Synchronous accessor for testing & manager-level queries."""
        return list(self._log.get(conversation_id, []))
