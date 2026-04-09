from pydantic import BaseModel

class DocumentIngestionResponse(BaseModel):
    file_name: str
    raw_path: str
    text_path: str
    content_preview: str
    tenant_id: str | None = None
    doc_id: str | None = None
    chunks_indexed: int | None = None
