FROM python:3.12-slim
WORKDIR /app
COPY apps/api/pyproject.toml ./
RUN pip install .
COPY apps/api/app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
