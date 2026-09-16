FROM apache/airflow:2.10.4-python3.11

# Build context is the repo root (see airflow/docker-compose.yaml -> build.context: ..)
# so the pipeline's own requirements.txt is available here.
COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt
