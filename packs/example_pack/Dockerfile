FROM python:3.12-slim

WORKDIR /app

COPY manifest.yaml entrypoint.py ./

# No USER here. The backend runs the container as the calling user so that files landing
# in the mounted /output are owned by the analyst rather than by root.
ENTRYPOINT ["python", "./entrypoint.py"]
