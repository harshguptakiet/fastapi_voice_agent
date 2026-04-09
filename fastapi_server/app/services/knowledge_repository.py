from __future__ import annotations

import json

from sqlalchemy import func

from app.core.database import SessionLocal, engine
from app.models.knowledge_chunk import KnowledgeChunk


class KnowledgeRepository:
    def __init__(self) -> None:
        self._initialized = False

    def _ensure_table(self) -> None:
        if self._initialized:
            return
        KnowledgeChunk.__table__.create(bind=engine, checkfirst=True)
        self._initialized = True

    def replace_document_chunks(
        self,
        *,
        tenant_id: str,
        doc_id: str,
        rows: list[dict],
    ) -> int:
        self._ensure_table()
        with SessionLocal() as db:
            db.query(KnowledgeChunk).filter(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.doc_id == doc_id,
            ).delete(synchronize_session=False)

            for row in rows:
                db.add(
                    KnowledgeChunk(
                        tenant_id=tenant_id,
                        doc_id=doc_id,
                        chunk_id=row["chunk_id"],
                        source_identifier=row.get("source_identifier"),
                        text=row["text"],
                        embedding_json=json.dumps(row["embedding"]),
                        metadata_json=json.dumps(row["metadata"]),
                    )
                )

            db.commit()
        return len(rows)

    def delete_document(self, *, tenant_id: str, doc_id: str) -> int:
        self._ensure_table()
        with SessionLocal() as db:
            deleted = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.doc_id == doc_id,
            ).delete(synchronize_session=False)
            db.commit()
            return int(deleted)

    def count_chunks(self) -> int:
        self._ensure_table()
        with SessionLocal() as db:
            total = db.query(func.count(KnowledgeChunk.id)).scalar() or 0
        return int(total)

    def count_chunks_for_tenant(self, tenant_id: str) -> int:
        self._ensure_table()
        with SessionLocal() as db:
            total = (
                db.query(func.count(KnowledgeChunk.id))
                .filter(KnowledgeChunk.tenant_id == tenant_id)
                .scalar()
                or 0
            )
        return int(total)


knowledge_repository = KnowledgeRepository()
