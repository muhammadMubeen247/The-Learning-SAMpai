FROM python:3.11-slim

WORKDIR /app

# System dependencies:
#   gcc / g++         — compile native extensions (asyncpg, lxml, etc.)
#   libgl1            — OpenCV / Docling image processing
#   libglib2.0-0      — GLib (OpenCV dependency)
#   libgomp1          — OpenMP for Docling's torch-based models
#   libmagic1         — python-magic file-type detection
#   poppler-utils     — PDF page rendering (pdfimages, pdftotext used by Docling)
#   tesseract-ocr     — OCR fallback for scanned PDFs in Docling
#   postgresql-client — pg_isready health checks + psql debugging
#   NOTE: libreoffice intentionally omitted — Docling uses python-pptx natively for
#   PPTX files (MsPowerpointDocumentBackend) and does not need LibreOffice.
#   Including libreoffice adds 500MB+ and 200+ packages to the image for no benefit.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir keeps image size down
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Docling downloads models on first use to ~/.cache — persist via volume if needed
# ChromaDB data directory (mounted as volume in docker-compose)
ENV CHROMA_DATA_DIR=/app/chroma_data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
