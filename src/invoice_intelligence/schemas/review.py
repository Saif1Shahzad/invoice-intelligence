"""Value-only review requests: clients cannot supply source boxes or model status."""
from typing import Annotated, Literal
from pydantic import Field
from invoice_intelligence.schemas.extraction import ContractModel

Text = Annotated[str, Field(min_length=1, max_length=1000)]
Value = Annotated[str, Field(max_length=10000)] | None

class ReviewAction(ContractModel):
    expected_revision: int = Field(ge=0)
    actor: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Text

class LineValues(ContractModel):
    source_index: int | None = Field(default=None, ge=0)
    description: Value = None
    sku: Value = None
    quantity: Value = None
    unit_price: Value = None
    amount: Value = None
    discount_amount: Value = None
    tax_rate: Value = None

class TaxValues(ContractModel):
    source_index: int | None = Field(default=None, ge=0)
    rate: Value = None
    amount: Value = None

class ReviewUpdate(ReviewAction):
    verified_fields: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=500)
    fields: dict[str, Value] = Field(default_factory=dict, max_length=30)
    line_items: list[LineValues] | None = Field(default=None, max_length=500)
    taxes: list[TaxValues] | None = Field(default=None, max_length=100)

class ReviewDecision(ReviewAction):
    decision: Literal['approved', 'rejected']
    acknowledge_warnings: bool = False
    matching_token: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')] | None = None
    acknowledge_po_exception: bool = False
