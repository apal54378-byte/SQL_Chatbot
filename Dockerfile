FROM python:3.13-slim

WORKDIR /app

# Inside a container, the database runs on the host machine, not localhost.
# This takes precedence over .env (which is excluded from the image anyway).
ENV DB_HOST=host.docker.internal
ENV DB_PORT=5432

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Pass secrets at runtime, e.g.:
# docker run -e GROQ_API_KEY=... -e DB_USER=... -e DB_PASSWORD=... -e DB_NAME=... -p 8501:8501 <image>
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
