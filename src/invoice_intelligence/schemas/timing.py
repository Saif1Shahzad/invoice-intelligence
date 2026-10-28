from typing import Annotated,Literal
from uuid import UUID
from pydantic import Field
from invoice_intelligence.schemas.extraction import ContractModel

class SessionStart(ContractModel):
    session_id: UUID
    actor: Annotated[str,Field(min_length=1,max_length=80)]
    kind: Literal['human','automated_demo']='human'

class TimeEvent(ContractModel):
    sequence: Annotated[int,Field(ge=1,le=100000)]
    active_ms: Annotated[int,Field(ge=0,le=86400000)]
    ended: bool=False
