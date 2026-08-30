from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud
import httpx

router = APIRouter()

@router.post("/run")
async def run_sync(changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://duty_sync:8001/run",
                params={"admin_name": changer, "admin_pin": pin},
                timeout=300
            )
            data = resp.json()
            if resp.status_code != 200 or not data.get("success"):
                raise HTTPException(status_code=500, detail=data.get("error", "Sync failed"))
            return {"success": True, "message": "Sync completed"}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Sync service unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))