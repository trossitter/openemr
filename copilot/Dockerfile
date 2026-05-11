FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create dirs and make entrypoint executable before dropping privileges
RUN mkdir -p /var/log/copilot /data/chroma && chmod +x entrypoint.sh

# Run as non-root
RUN useradd -m copilot && chown -R copilot /app /var/log/copilot /data/chroma
USER copilot

# Pre-download the ChromaDB ONNX embedding model so the first query doesn't
# trigger a 79 MB download mid-request (which causes search_guidelines to time out).
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

EXPOSE 8400

CMD ["./entrypoint.sh"]
