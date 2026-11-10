"""Anonymous usage events reported by the browser."""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.services.product_events import record

router = APIRouter(prefix="/events", tags=["events"])


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["setup_started", "setup_finished", "first_number_seen", "payday_link_clicked"]


@router.post("", status_code=204)
def post_event(body: EventIn, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    record(db, user_id, body.name)
    return Response(status_code=204)
