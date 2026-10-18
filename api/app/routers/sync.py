from fastapi import APIRouter, Depends, HTTPException, Request
from .. import models
from ..security import require_admin
import httpx

router = APIRouter()

@router.post("/run")
async def run_sync(request: Request, user: models.User = Depends(require_admin)):
    # Токен вызывающего передаём в sync-сервис как есть: он проверит подпись и
    # роль сам. PIN для этого больше не нужен и никуда не передаётся.
    auth_header = request.headers.get("authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://duty_sync:8001/run",
                headers={"Authorization": auth_header},
                timeout=300
            )
            data = resp.json()
            if resp.status_code != 200 or not data.get("success"):
                raise HTTPException(status_code=500, detail=data.get("error", "Sync failed"))
            return {"success": True, "message": "Sync completed"}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Sync service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
