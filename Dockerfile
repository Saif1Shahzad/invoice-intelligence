FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd tesseract-ocr-fra tesseract-ocr-spa tesseract-ocr-deu ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home invoice && mkdir -p /app /data && chown invoice:invoice /app /data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .
COPY deploy/entrypoint.sh /entrypoint.sh
USER invoice
ENV INVOICE_DATA_DIR=/data
ENTRYPOINT ["sh", "/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "invoice_intelligence.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
