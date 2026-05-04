import os

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse

from app.routes.auth import authenticate
from app.utils import BASE_DIR, FILE_FOLDER

router = APIRouter(tags=["Files"])


@router.get("/files")
def get_files():
    files = []

    for filename in os.listdir(FILE_FOLDER):
        path = os.path.join(FILE_FOLDER, filename)

        if os.path.isfile(path):
            files.append({
                "filename": filename,
                "url": f"/uploads/files/{filename}",
                "size": os.path.getsize(path)
            })

    return files


@router.delete("/files/{filename}")
def delete_file(filename: str):
    file_path = os.path.join(FILE_FOLDER, filename)

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