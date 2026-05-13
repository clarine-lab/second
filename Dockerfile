FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 7860
CMD ["gunicorn", "--timeout", "600", "--workers", "2", "-b", "0.0.0.0:7860", "app:app"]
