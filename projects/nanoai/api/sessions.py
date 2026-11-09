from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from aicore.session import SessionDumpPayload, SessionOutput, SessionSubmission

from projects.nanoai.api.schemas import (
    CreateSessionRequest,
    SessionCreatedResponse,
    SessionRestoredResponse,
    SessionView,
    SubmitTurnRequest,
)
from projects.nanoai.runtime import (
    SessionBusyError,
    SessionClosedError,
    SessionStateUpdateUnsupportedError,
    SessionRestoreError,
    SessionTurnNotCancellableError,
    SessionTurnNotFoundError,
    V1AgentSession,
)
from projects.nanoai.service import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionService,
)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post(
    "", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED
)
async def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionCreatedResponse:
    session = service.create(
        payload.config, context=payload.context, metadata=payload.metadata
    )
    return SessionCreatedResponse(session_id=session.id)


@router.post(
    "/restore",
    response_model=SessionRestoredResponse,
    status_code=status.HTTP_201_CREATED,
)
async def restore_session(
    payload: SessionDumpPayload,
    service: SessionService = Depends(get_session_service),
) -> SessionRestoredResponse:
    try:
        session = service.restore(payload)
    except SessionAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except SessionRestoreError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return SessionRestoredResponse(session_id=session.id)


@router.get("/{session_id}/dump", response_model=SessionDumpPayload)
async def dump_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> SessionDumpPayload:
    try:
        return await service.dump(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except SessionBusyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.get("/{session_id}", response_model=SessionView)
async def get_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> SessionView:
    session = _get_session_or_404(service, session_id)
    return _session_view(session)


@router.post("/{session_id}/turns")
async def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    service: SessionService = Depends(get_session_service),
) -> StreamingResponse:
    try:
        session, submission, outputs = service.submit(
            session_id,
            payload.input,
            state_update=payload.state_update,
        )
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except (SessionBusyError, SessionClosedError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except SessionStateUpdateUnsupportedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    return StreamingResponse(
        _stream_turn(session, submission, outputs),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-NanoAI-Turn-Id": submission.turn_id,
        },
    )


@router.post("/{session_id}/turns/{turn_id}/cancel")
async def cancel_turn(
    session_id: str,
    turn_id: str,
    service: SessionService = Depends(get_session_service),
) -> Any:
    try:
        return await service.cancel(session_id, turn_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except SessionTurnNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except SessionTurnNotCancellableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> Response:
    try:
        await service.close(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _stream_turn(
    session: V1AgentSession,
    submission: SessionSubmission,
    outputs: AsyncIterator[SessionOutput],
) -> AsyncIterator[str]:
    yield _sse("session.submitted", submission.model_dump(mode="json"))
    async for output in outputs:
        yield _sse("session.output", output.model_dump(mode="json"))

    turn = next(turn for turn in session.state.history if turn.id == submission.turn_id)
    yield _sse("session.turn.finished", turn.model_dump(mode="json"))


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_session_or_404(service: SessionService, session_id: str) -> V1AgentSession:
    try:
        return service.get(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


def _session_view(session: V1AgentSession) -> SessionView:
    return SessionView(
        session_id=session.id,
        context=session.context,
        state=session.state,
        metadata=dict(session.metadata),
    )
