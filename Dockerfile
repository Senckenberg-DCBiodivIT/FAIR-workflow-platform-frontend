FROM python:3.12.3-alpine

# git is required to get packages in requirements.txt that are pulled from git
RUN apk upgrade && apk add git

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip --no-cache-dir
RUN pip install -r requirements.txt --no-cache-dir

# set work directory
COPY cwr_frontend/manage.py .
COPY cwr_frontend/cwr_frontend /app/cwr_frontend
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh
ENTRYPOINT ["/bin/sh", "entrypoint.sh"]
