from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.config import get_settings
from app.core.metrics import DOCUMENTS_UPLOADED_TOTAL
from app.core.rate_limit import limiter
from app.db.models.document_chunk import DocumentChunk
from app.db.models.user import User
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.services.documents import (
    delete_document,
    get_document,
    list_user_documents,
    upload_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _get_chunk_count(db: AsyncSession, document_id: str) -> int:
    """Get the number of chunks for a document."""
    result = await db.execute(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
    )
    return result.scalar() or 0


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(get_settings().rate_limit_upload)
async def upload_document_endpoint(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentUploadResponse:
    """Upload a document."""
    document = await upload_document(db, current_user, file)
    DOCUMENTS_UPLOADED_TOTAL.labels(user_id=str(current_user.id)).inc()
    return DocumentUploadResponse.model_validate(document)


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = 50,
    offset: int = 0,
) -> DocumentListResponse:
    """List all documents for the authenticated user."""
    documents, total = await list_user_documents(db, current_user.id, limit, offset)

    # Build response with chunk counts
    doc_responses = []
    for doc in documents:
        chunk_count = await _get_chunk_count(db, str(doc.id))
        doc_dict = doc.__dict__.copy()
        doc_dict["chunk_count"] = chunk_count
        doc_dict["content_excerpt"] = doc.content_excerpt
        doc_responses.append(DocumentResponse.model_validate(doc_dict))

    return DocumentListResponse(
        documents=doc_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_user_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentResponse:
    """Get details of a specific user document."""
    document = await get_document(db, current_user.id, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunk_count = await _get_chunk_count(db, document_id)
    doc_dict = document.__dict__.copy()
    doc_dict["chunk_count"] = chunk_count
    doc_dict["content_excerpt"] = document.content_excerpt
    return DocumentResponse.model_validate(doc_dict)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Delete user document."""
    deleted = await delete_document(db, current_user.id, document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
