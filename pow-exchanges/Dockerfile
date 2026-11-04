FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY powx ./powx
COPY sources.json .
VOLUME /data
EXPOSE 8000
# ANTHROPIC_API_KEY (and optionally POWX_MODEL) must be passed at run time.
CMD ["python", "-m", "powx.server", "--db", "/data/powx.db", "--host", "0.0.0.0", "--port", "8000"]
