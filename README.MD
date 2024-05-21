# Crop wild relatives demo frontend

Demo frontend for the crop wild relatives usecase.

## Build

`docker build -t cwr-frontend .`

## Deployment

The environment variable `CORDRA_URL` needs to point to a running cordra instance with no password protection for accessing relevant objects and payloads. Only reads objects of the type "Dataset". The docker image listens on port 8000.
