FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PAPERPILOT_TORCH_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/opt/models
RUN python -c "from sentence_transformers import SentenceTransformer,CrossEncoder; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
COPY api ./api
COPY auth ./auth
COPY conversations ./conversations
COPY database ./database
COPY Graph_Rag ./Graph_Rag
COPY main.py worker.py browser_access.py deploy_app.py start_service.py ./
COPY seed ./seed
CMD ["python", "-u", "start_service.py"]
