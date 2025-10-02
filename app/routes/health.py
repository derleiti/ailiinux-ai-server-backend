from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/health", tags=["Monitoring"], summary="Health check endpoint")
async def health_check():
    # Here you could add checks for database connection, external services, etc.
    # For now, a simple success response is sufficient.
    return JSONResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)
