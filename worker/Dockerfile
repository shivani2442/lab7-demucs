FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
COPY worker/requirements.txt worker-requirements.txt
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt -r worker-requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir Cython==0.29.37 \
    && pip install --no-cache-dir --no-build-isolation diffq==0.2.4 \
    && rm -rf /var/lib/apt/lists/*
COPY common.py .
COPY worker/worker.py worker/worker.py
ENV PYTHONUNBUFFERED=1 TORCH_HOME=/models
CMD ["python", "-m", "worker.worker"]
