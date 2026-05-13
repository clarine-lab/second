FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your proxy script
COPY . .

# Expose port 7860 for Hugging Face
EXPOSE 7860

# Use the gevent worker with a generous timeout for DeepSeek's 'thinking' phase
CMD ["gunicorn", "-w", "2", "-k", "gevent", "--timeout", "600", "-b", "0.0.0.0:7860", "app:app"]
