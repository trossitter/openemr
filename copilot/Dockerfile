FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create log directory
RUN mkdir -p /var/log/copilot

# Run as non-root
RUN useradd -m copilot && chown -R copilot /app /var/log/copilot
USER copilot

EXPOSE 8400

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8400", "--log-level", "warning"]
