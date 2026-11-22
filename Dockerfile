FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_THREAD_LIMIT=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-pol tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --no-deps \
    'anon-legal-pl @ https://codeload.github.com/Dymirt/anon-legal-pl/tar.gz/ed24629fd3a4d81f114390bebffcbc22d31e632c#sha256=0ecb91e1f8741373dc9878622186c704eb2423b8c34eeb58371d8673d0e27d38'
COPY odwolania ./odwolania

ENTRYPOINT ["python", "-m", "odwolania"]
