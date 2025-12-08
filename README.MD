# FAIR workflow platform frontend for Crop wild relatives use case

Frontend for the FAIR workflow platform for the crop wild relatives usecase.
This is part of the [FAIR workflow platform](https://github.com/dnlbauer/FAIR-workflow-platform).

## Build

`docker build -t cwr-frontend .`

## Deployment


`docker run -d -p 8000:8000 --env-file .env cwr-frontend`

### Environment variables

- ALLOWED_HOSTS: Hosts allowed to connect to this instance. Set to the server's ip/domain
- CORDRA_URL: URL of a running cordra instance with no password protection for accessing relevant objects and payloads. The frontend lists objects of type "Dataset" and traverses the graph of linked objects to find associated objects relevant to the dataset.
- CORDRA_PREFIX: Prefix for cordra objects
- CORDRA_USER: Username used for accessing cordra, leave blank for anonymous access
- CORDRA_PASSWORD: Password for accessing corda
- WORKFLOW_SERVICE_URL: URL of the workflow service to submit workflows to
- WORKFLOW_SERVICE_USER: Workflow service user for Basic auth
- WORKFLOW_SERVICE_PASSWORD: Password of Workflow service user
- ARGO_URL: Base URL of argo workflow engine. Used to render links from workflow status list
- ORCID_BASE_DOMAIN: Which base domain to use for ORCID. I.e. sandbox.orcid.org or orcid.org (default: orcid.org)
- ORCID_CLIENT_ID: ORCID client id
- ORCID_SECRET: ORCID client secret
- ORCID_ALLOW_LIST: List of ORCID user ids to allow to use the workflow service (comma-separated)
- ORCID_ADMIN_LIST: List of ORCID user ids to allow to access the admin interface (comma-separated)
- DEBUG: toggle djangos debugging output
- ALLOWED_HOSTS: django allowed host names (comma-separated)
- FORCE_SCRIPT_NAME: must be set to make the frontend available under a subpath like /cwr
- SECRET_KEY: Django secret key
- PROJECT_NAME: Name of the project, used in the UI
- DB_PATH: Path to the django database

## Administration

Add API keys with the management command:

`python manage.py create_api_key --orcid <user-orcid> --name <user-name>`

## License

Licensed under the [MIT](./LICENSE) license.
