FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential curl

COPY . .

RUN pip install pipx && pipx install uv
ENV PATH="/root/.local/bin:$PATH"

RUN uv pip install --no-cache-dir --system -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]