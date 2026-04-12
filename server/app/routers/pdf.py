from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.deps import get_current_user
from app.schemas import PdfExtractResponse
from app.services.auth_users import UserRecord
from app.services.pdf_extract import extract_pdf_bytes

router = APIRouter(prefix="/pdf", tags=["pdf"])


@router.post("/extract", response_model=PdfExtractResponse)
async def extract_pdf_upload(
    file: UploadFile = File(...),
    _: UserRecord = Depends(get_current_user),
) -> PdfExtractResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a .pdf file")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    try:
        data = extract_pdf_bytes(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF parse error: {e}") from e
    return PdfExtractResponse(**data)
