FROM python:3.12-slim

WORKDIR /app

COPY manifest.yaml entrypoint.py ./

USER nobody

ENTRYPOINT ["python", "./entrypoint.py"]
