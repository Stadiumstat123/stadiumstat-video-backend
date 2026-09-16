FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data MODEL_DIR=/models DEVICE=cpu
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgomp1 util-linux && rm -rf /var/lib/apt/lists/*
# Explicit CPU wheel pair. Use matching CUDA wheels on a GPU deployment.
RUN pip install --no-cache-dir torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service ./service
COPY start.sh ./start.sh
RUN useradd --create-home stadium && mkdir /data /models && chown -R stadium:stadium /data /models /app
USER stadium
RUN python -m service.prepare
USER root
EXPOSE 8000
CMD ["sh", "/app/start.sh"]
