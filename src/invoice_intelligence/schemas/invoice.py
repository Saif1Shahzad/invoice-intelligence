from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Money = Annotated[Decimal, Field(allow_inf_nan=False)]


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    net_amount: Money


class Invoice(BaseModel):
    """Tax-exclusive validation input, not the future nullable extraction schema."""

    model_config = ConfigDict(extra="forbid")
    supplier_name: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_mode: Literal["exclusive"]
    line_items: list[LineItem] = Field(min_length=1)
    subtotal: Money
    document_discount: Money
    shipping: Money
    tax: Money
    total: Money
    rounding_tolerance: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] = Decimal("0.01")
