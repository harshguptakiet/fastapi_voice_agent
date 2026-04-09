from sqlalchemy import Column, DateTime, String, func

from app.core.database import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    session_id = Column(String(64), primary_key=True, index=True)
    current_topic = Column(String(255), nullable=True)
    language = Column(String(32), nullable=False, default="en")
    persona = Column(String(64), nullable=False, default="default")
    last_response = Column(String(2000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
