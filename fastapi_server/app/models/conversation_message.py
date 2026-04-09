from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        String(64),
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
