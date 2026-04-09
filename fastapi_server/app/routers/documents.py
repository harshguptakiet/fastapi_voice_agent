from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from app.dependencies import get_tenant_id
from app.services.document_service import document_service
from app.services.knowledge_service import knowledge_service
from app.schemas.document import DocumentIngestionResponse

router = APIRouter(prefix="/documents", tags=["documents"])



@router.post("/upload", response_model=DocumentIngestionResponse)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    topic: str | None = Query(default=None),
    language: str = Query(default="en"),
):
    # Validate extension
    allowed_extensions = {".pdf", ".docx", ".pptx"}
    ext = f".{file.filename.split('.')[-1].lower()}"
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
        )

    content = await file.read()
    result = await document_service.save_and_extract(file.filename, content)

    doc_id = Path(file.filename).stem
    extracted_text = result.get("extracted_text") or ""

    chunks_indexed = 0
    if extracted_text.strip():
        chunks_indexed = await knowledge_service.reindex_document(
            tenant_id=tenant_id,
            doc_id=doc_id,
            text=extracted_text,
            topic=topic,
            language=language,
            source_uri=result.get("raw_path"),
            metadata={
                "document_name": file.filename,
                "document_version": "v1",
            },
        )

    result["tenant_id"] = tenant_id
    result["doc_id"] = doc_id
    result["chunks_indexed"] = chunks_indexed

    return result

@router.get("/list")
async def list_documents():
    docs = document_service.list_documents()
    return {"documents": docs}
