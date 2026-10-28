from typing import Annotated, Literal
from pydantic import Field
from invoice_intelligence.schemas.review import ReviewAction

class DuplicateDecision(ReviewAction):
    other_document_id: Annotated[str,Field(min_length=1,max_length=80)]
    matching_token: Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
    decision: Literal['same_bill','different_bill','unresolved']
    canonical_document_id: str | None = None
