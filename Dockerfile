FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOVELFORGE_WORKSPACE_DIR=/data/novelforge \
    NOVELFORGE_PUBLIC_MODE=1

WORKDIR /app
COPY . /app
RUN python -m zipfile -e NovelForge_v0.3_online_mobile.zip /tmp/novelforge_bundle \
    && cp -a /tmp/novelforge_bundle/NovelForge/. /app/ \
    && rm -rf /tmp/novelforge_bundle
RUN pip install --no-cache-dir .
RUN mkdir -p /data/novelforge

EXPOSE 8501
VOLUME ["/data/novelforge"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; p=os.getenv('PORT','8501'); urllib.request.urlopen('http://127.0.0.1:'+p+'/_stcore/health', timeout=3)"

CMD ["sh", "-c", "streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]
