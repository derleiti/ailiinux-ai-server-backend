from __future__ import annotations

from fastapi import HTTPException, status


def api_error(message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST, code: str = "bad_request") -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"message": message, "code": code}})
