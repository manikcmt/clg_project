from fastapi import HTTPException, UploadFile


MAX_PICTURE_SIZE = 5 * 1024 * 1024


async def read_picture(picture: UploadFile | None) -> tuple[bytes | None, str | None]:
    if picture is None or not picture.filename:
        return None, None

    data = await picture.read(MAX_PICTURE_SIZE + 1)
    if len(data) > MAX_PICTURE_SIZE:
        raise HTTPException(status_code=413, detail="Picture must be 5 MB or smaller.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return data, "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return data, "image/webp"
    raise HTTPException(status_code=400, detail="Upload a valid JPG, PNG, or WEBP picture.")
