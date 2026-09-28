"""HTTP routes for the AI Copilot module.

All routes require ``copilot:use`` and act on the **caller's own** conversations.
``/copilot/ask`` answers a one-off question without persistence; asking within a
conversation persists both the question and the grounded answer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CopilotServiceDep, UowDep, require_permission
from app.modules.copilot.schemas import (
    AnswerResult,
    AskRequest,
    AskResponse,
    ConversationCreateRequest,
    ConversationResponse,
    GenericMessage,
    MessageResponse,
    PaginatedConversations,
)

router = APIRouter(tags=["AI Copilot"])


@router.post(
    "/copilot/ask",
    response_model=AnswerResult,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="Ask a one-off question",
)
def ask_adhoc(payload: AskRequest, service: CopilotServiceDep) -> AnswerResult:
    """Answer a natural-language question without saving a conversation."""
    return service.ask_adhoc(question=payload.question, context=payload.context)


@router.post(
    "/copilot/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="Start a conversation",
)
def create_conversation(
    payload: ConversationCreateRequest, service: CopilotServiceDep, uow: UowDep
) -> ConversationResponse:
    """Start a new conversation owned by the caller."""
    conversation = service.create_conversation(title=payload.title)
    uow.commit()
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/copilot/conversations",
    response_model=PaginatedConversations,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="List my conversations",
)
def list_conversations(
    service: CopilotServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedConversations:
    """Return a page of the caller's own conversations (newest first)."""
    items, total = service.search_conversations(limit=limit, offset=offset)
    return PaginatedConversations(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/copilot/conversations/{conversation_id}",
    response_model=ConversationResponse,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="Get one of my conversations",
)
def get_conversation(
    conversation_id: uuid.UUID, service: CopilotServiceDep
) -> ConversationResponse:
    """Return one of the caller's own conversations."""
    return ConversationResponse.model_validate(service.get_conversation(conversation_id))


@router.get(
    "/copilot/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="List a conversation's messages",
)
def list_messages(conversation_id: uuid.UUID, service: CopilotServiceDep) -> list[MessageResponse]:
    """Return the messages of one of the caller's conversations."""
    return [MessageResponse.model_validate(m) for m in service.list_messages(conversation_id)]


@router.post(
    "/copilot/conversations/{conversation_id}/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="Ask a question in a conversation",
)
def ask_in_conversation(
    conversation_id: uuid.UUID,
    payload: AskRequest,
    service: CopilotServiceDep,
    uow: UowDep,
) -> AskResponse:
    """Answer a question in a conversation, persisting both turns."""
    conversation, message, result = service.ask_in_conversation(
        conversation_id, question=payload.question, context=payload.context
    )
    uow.commit()
    return AskResponse(
        conversation_id=conversation.id,
        question=payload.question,
        intent=result.intent,
        answer=result.answer,
        grounding=result.grounding,
        assistant_message_id=message.id,
    )


@router.delete(
    "/copilot/conversations/{conversation_id}",
    response_model=GenericMessage,
    dependencies=[Depends(require_permission("copilot:use"))],
    summary="Delete one of my conversations",
)
def delete_conversation(
    conversation_id: uuid.UUID, service: CopilotServiceDep, uow: UowDep
) -> GenericMessage:
    """Soft-delete one of the caller's conversations and its messages."""
    service.delete_conversation(conversation_id)
    uow.commit()
    return GenericMessage(detail="Conversation deleted.")
