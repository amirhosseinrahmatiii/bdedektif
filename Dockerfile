FROM mcr.microsoft.com/azure-functions/python:4-python3.10

RUN apt-get update && \
    apt-get install -y unixodbc unixodbc-dev gcc g++ curl && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18

COPY requirements.txt /app/
WORKDIR /app
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app"]
