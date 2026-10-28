"""Day-2 extraction contract. Separate from the Day-1 arithmetic API input."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]
NonemptyText = Annotated[str, Field(min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(ContractModel):
    """Upright-page coordinates; page numbers start at one."""

    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    text: NonemptyText
    method: Literal["pdf_text", "ocr", "human"]
    span_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_box(self):
        x0, y0, x1, y1 = self.bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("bbox must be ordered, nonempty, normalized to [0,1]")
        return self


class ExtractedField(ContractModel, Generic[T]):
    value: T | None = None
    status: Literal["observed", "missing", "ambiguous", "corrected", "proposed"] = "missing"
    reason: str | None = "not_extracted"
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == "observed":
            if self.value is None or not self.evidence:
                raise ValueError("observed requires a value and source evidence")
            if self.reason is not None:
                raise ValueError("observed uses reason=null")
        elif self.status == "proposed":
            if self.value is None or not self.reason or not self.evidence:
                raise ValueError("proposed requires a value, review reason and original source context")
        elif self.status == "corrected":
            if self.value is None or not self.reason:
                raise ValueError("corrected requires a value and reviewer reason; evidence is original context only")
        elif self.value is not None or not self.reason:
            raise ValueError("missing/ambiguous requires value=null and a reason")
        return self


class ExtractedLineItem(ContractModel):
    description: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    sku: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    quantity: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    unit_price: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    amount: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    discount_amount: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    tax_rate: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)


class ExtractedTax(ContractModel):
    rate: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    amount: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)


class InvoiceExtraction(ContractModel):
    """Source observations or explicit human corrections; derived values stay separate."""

    schema_version: Literal["1.0"] = "1.0"
    document_id: NonemptyText
    document_type: ExtractedField[Literal["invoice", "credit_note", "receipt"]] = Field(default_factory=ExtractedField)
    supplier_name: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    supplier_address: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    customer_name: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    invoice_number: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    issue_date: ExtractedField[date] = Field(default_factory=ExtractedField)
    due_date: ExtractedField[date] = Field(default_factory=ExtractedField)
    currency: ExtractedField[Annotated[str, Field(pattern=r"^[A-Z]{3}$")]] = Field(default_factory=ExtractedField)
    po_number: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    tax_mode: ExtractedField[Literal["exclusive", "inclusive", "reverse_charge"]] = Field(default_factory=ExtractedField)
    subtotal: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    document_discount: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    shipping: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    tax_amount: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    tax_rate: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    total: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    tip: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    service_fee: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    previous_balance: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    amount_paid: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    amount_due: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    payment_terms: ExtractedField[NonemptyText] = Field(default_factory=ExtractedField)
    conditional_discount_rate: ExtractedField[FiniteDecimal] = Field(default_factory=ExtractedField)
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    taxes: list[ExtractedTax] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
