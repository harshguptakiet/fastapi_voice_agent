from __future__ import annotations

from typing import Any

from app.core.database import Base, engine
from app.core.database import SessionLocal
from app.models.conversation_session import ConversationSession


class ContextService:
    def __init__(self) -> None:
        Base.metadata.create_all(
            bind=engine,
            tables=[
                ConversationSession.__table__,
            ],
        )

    def exists(self, session_id: str) -> bool:
        with SessionLocal() as db:
            return (
                db.query(ConversationSession)
                .filter(ConversationSession.session_id == session_id)
                .first()
                is not None
            )

    def get(self, session_id: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            sess = (
                db.query(ConversationSession)
                .filter(ConversationSession.session_id == session_id)
                .first()
            )
            if not sess:
                return None
            return {
                "current_topic": sess.current_topic,
                "language": sess.language,
                "persona": sess.persona,
                "last_response": sess.last_response,
            }

    def set(self, session_id: str, data: dict[str, Any]) -> None:
        with SessionLocal() as db:
            sess = (
                db.query(ConversationSession)
                .filter(ConversationSession.session_id == session_id)
                .first()
            )
            if not sess:
                sess = ConversationSession(
                    session_id=session_id,
                    current_topic=data.get("current_topic"),
                    language=data.get("language") or "en",
                    persona=data.get("persona") or "default",
                    last_response=data.get("last_response"),
                )
                db.add(sess)
            else:
                if "current_topic" in data:
                    sess.current_topic = data.get("current_topic")
                if "language" in data:
                    sess.language = data.get("language") or "en"
                if "persona" in data:
                    sess.persona = data.get("persona") or "default"
                if "last_response" in data:
                    sess.last_response = data.get("last_response")
            db.commit()

    def update_state(self, session_id: str, key: str, value: Any) -> bool:
        with SessionLocal() as db:
            sess = (
                db.query(ConversationSession)
                .filter(ConversationSession.session_id == session_id)
                .first()
            )
            if not sess:
                return False

            if key == "current_topic":
                sess.current_topic = value
            elif key == "language":
                sess.language = value or "en"
            elif key == "persona":
                sess.persona = value or "default"
            elif key == "last_response":
                sess.last_response = value
            else:
                return False

            db.commit()
            return True

    def reset(self, session_id: str) -> None:
        with SessionLocal() as db:
            db.query(ConversationSession).filter(
                ConversationSession.session_id == session_id
            ).delete()
            db.commit()

    def get_messages(self, session_id: str):
        # Deprecated: conversation messages are persisted via Redis-backed ConversationMemoryService.
        _ = session_id
        return []

    def add_message(self, session_id: str, *, role: str, content: str) -> bool:
        # Deprecated: conversation messages are persisted via Redis-backed ConversationMemoryService.
        _ = session_id, role, content
        return True


context = ContextService()
