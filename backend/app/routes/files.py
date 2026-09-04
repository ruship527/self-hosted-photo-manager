import os
import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse

from app.routes.auth import authenticate
from app.utils import (
    BASE_DIR,
    FILE_FOLDER,
    MAX_UPLOAD_MB,
    MAX_UPLOAD_BYTES,
    sanitize_filename,
    safe_join,
    save_upload,
)

router = APIRouter(tags=["Files"])


@router.get("/files")
def get_files(user: str = Depends(authenticate)):
    files = []

    os.makedirs(FILE_FOLDER, exist_ok=True)

    for filename in os.listdir(FILE_FOLDER):
        path = os.path.join(FILE_FOLDER, filename)

        if os.path.isfile(path):
            files.append({
                "filename": filename,
                "url": f"/uploads/files/{filename}",
                "size": os.path.getsize(path)
            })

    return files


@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...), user: str = Depends(authenticate)):
    os.makedirs(FILE_FOLDER, exist_ok=True)

    try:
        safe_name = sanitize_filename(file.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(FILE_FOLDER, safe_name)

    # Avoid clobbering an existing file of the same name
    if os.path.exists(file_path):
        base, ext = os.path.splitext(safe_name)
        safe_name = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(FILE_FOLDER, safe_name)

    try:
        save_upload(file, file_path, MAX_UPLOAD_BYTES)
    except ValueError:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_MB}MB upload limit")

    return {
        "message": "File uploaded successfully",
        "filename": safe_name
    }


@router.delete("/files/{filename}")
def delete_file(filename: str, user: str = Depends(authenticate)):
    try:
        file_path = safe_join(FILE_FOLDER, filename)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)

    return {
        "message": "File deleted successfully",
        "filename": filename
    }


@router.get("/files-page")
def files_page(user: str = Depends(authenticate)):
    return FileResponse(os.path.join(BASE_DIR, "frontend", "files.html"))