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

EXPOSE 8400

CMD ["./entrypoint.sh"]
