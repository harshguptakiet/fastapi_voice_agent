from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, func

from app.core.database import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_id", "chunk_id", name="uq_knowledge_chunk_tenant_doc_chunk"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    doc_id = Column(String(255), nullable=False, index=True)
    chunk_id = Column(String(64), nullable=False, index=True)
    source_identifier = Column(String(255), nullable=True)

    text = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
