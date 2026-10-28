"""Explicit local settings. Environment variables are read on app/worker start."""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data/runtime")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 10
    max_pixels: int = 25_000_000
    render_dpi: int = 180
    inspect_timeout: int = 20
    process_timeout: int = 180
    ocr_timeout: int = 25
    max_attempts: int = 3
    max_text_chars: int = 500_000
    tesseract_cmd: str = "tesseract"
    extraction_provider: str = "local"

    groq_model: str = "qwen/qwen3.8-27b"
    groq_timeout: int = 35
    groq_max_tokens: int = 950
    groq_max_pages: int = 10
    groq_min_interval: int = 65
    groq_input_price: str = "0.80"
    groq_output_price: str = "4.00"
    groq_document_budget: str = "0.15"
    ocr_languages: str = "eng"
    ocr_enhanced: bool = False
    auth_file: str = ""
    deployment: str = "local"
    public_origin: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,testserver"

    def __post_init__(self):
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        if self.extraction_provider not in {"local", "disabled", "groq"}:
            raise ValueError("EXTRACTION_PROVIDER must be local, groq or disabled")
        import re
        from decimal import Decimal
        if not re.fullmatch(r'[A-Za-z0-9_./-]{1,120}',self.groq_model):raise ValueError('Invalid Groq model')
        if not 0<=self.groq_min_interval<=120:raise ValueError("Groq request interval must be between 0 and 120 seconds")
        if not 1<=self.groq_timeout<=40 or not 256<=self.groq_max_tokens<=16000 or not 1<=self.groq_max_pages<=10:raise ValueError('Groq limits are out of range')
        for name in ['groq_input_price','groq_output_price','groq_document_budget']:
            amount=Decimal(getattr(self,name))
            if not amount.is_finite() or amount<=0 or amount>100:raise ValueError('Invalid Groq cost limit')
        if not re.fullmatch(r'[a-z]{3}(?:\+[a-z]{3})*',self.ocr_languages):raise ValueError('Invalid OCR language setting')
        if self.deployment not in {'local','production'}:raise ValueError('Invalid deployment mode')
        if self.deployment=='production' and (not self.auth_file or not self.public_origin.startswith('https://')):raise ValueError('Production requires an auth file and an HTTPS public origin')
        for name in ["max_upload_bytes", "max_pages", "max_pixels", "render_dpi",
                     "inspect_timeout", "process_timeout", "ocr_timeout", "max_attempts", "max_text_chars"]:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def from_env(cls):
        from invoice_intelligence.environment import load_environment
        load_environment()
        return cls(data_dir=Path(os.getenv("INVOICE_DATA_DIR", "data/runtime")),
                   process_timeout=int(os.getenv("INVOICE_PROCESS_TIMEOUT","600" if os.getenv("EXTRACTION_PROVIDER")=="groq" else "180")),
                   max_upload_bytes=int(os.getenv("INVOICE_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
                   max_pages=int(os.getenv("INVOICE_MAX_PAGES", "10")),
                   max_pixels=int(os.getenv("INVOICE_MAX_PIXELS", "25000000")),
                   tesseract_cmd=os.getenv("TESSERACT_CMD", "tesseract"),
                   extraction_provider=os.getenv("EXTRACTION_PROVIDER", "local"),
                   groq_model=os.getenv("GROQ_MODEL","qwen/qwen3.8-27b"),
                   groq_timeout=int(os.getenv("GROQ_TIMEOUT","35")),
                   groq_max_tokens=int(os.getenv("GROQ_MAX_TOKENS","950")),
                   groq_min_interval=int(os.getenv("GROQ_MIN_INTERVAL","65")),
                   groq_document_budget=os.getenv("GROQ_DOCUMENT_BUDGET_USD","0.15"),
                   groq_input_price=os.getenv("GROQ_INPUT_PRICE_PER_MILLION","0.80"),
                   groq_output_price=os.getenv("GROQ_OUTPUT_PRICE_PER_MILLION","4.00"),
                   ocr_languages=os.getenv("OCR_LANGUAGES","eng"),
                   ocr_enhanced=os.getenv("OCR_ENHANCED","false").lower()=="true",
                   auth_file=os.getenv("INVOICE_AUTH_FILE",""),deployment=os.getenv("INVOICE_DEPLOYMENT","local"),
                   public_origin=os.getenv("INVOICE_PUBLIC_ORIGIN",""),
                   allowed_hosts=os.getenv("INVOICE_ALLOWED_HOSTS","localhost,127.0.0.1,testserver"))

    def child_options(self):
        return {name: getattr(self, name) for name in [
            "max_pages", "max_pixels", "render_dpi", "ocr_timeout", "max_text_chars", "tesseract_cmd",
            "extraction_provider", "groq_model", "groq_timeout", "groq_max_tokens", "groq_max_pages", "groq_min_interval",
            "groq_input_price", "groq_output_price", "groq_document_budget", "ocr_languages", "ocr_enhanced"]}
