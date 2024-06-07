# Crop wild relatives demo frontend

Demo frontend for the crop wild relatives usecase.

## Build

`docker build -t cwr-frontend .`

## Deployment
Configuration happens in `cwr_frontend/settings.py`.

### Environment variables

- ALLOWED_HOSTS: Hosts allowed to connect to this instance. Set to the server's ip/domain
- CORDRA_URL: URL of a running cordra instance with no password protection for accessing relevant objects and payloads. The frontend lists objects of type "Dataset" and traverses the graph of linked objects to find associated objects relevant to the dataset.
- DEBUG: toggle djangos debugging output
- FORCE_SCRIPT_NAME: must be set to make the frontend available under a subpath like /cwr
- SECRET_KEY: Django secret key

## API Access

The frontend proxies all requests made to `/api/.*` to cordra.
This can be used to access cordra from the frontend, create absolute links etc.
