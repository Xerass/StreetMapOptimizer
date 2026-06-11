FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests networkx matplotlib

#copies the entire folder from here.
COPY . .

#expose 5000, so we can call http//:localhost:5000 once docker is active.
EXPOSE 5000

CMD ["python", "app.py"]
