FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY data ./data
COPY scripts ./scripts
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser && mkdir -p runtime && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn","app.api.main:app","--host","0.0.0.0","--port","8000"]
