# Workflow API Usage

## Prepare RO-Crate

The RO-Crate is a zip folder and must contain at least two files: "ro-crate-metadata.json" and "workflow.yaml".

### Metadata Description

The ro-crate-metadata.json needs to follow the [Workflow RO-Crate](https://about.workflowhub.eu/Workflow-RO-Crate/) profile. You can use [this](hello-world/ro-crate-metadata.json) hello-world metadata file as a minimal example.
What you'll need to adapt to your use case:

- In the root dataset (with id = "./"):
    - Change name, description, keywords and license.
    - Change the author, that is referenced in the root dataset
- In the workflow.yaml object:
    - Change description
    - Optional: If the workflow has input parameters adapt them.

### Workflow Description

You can use [this](hello-world/workflow.yaml) hello-world workflow definition as a minimal example. And [here](https://argo-workflows.readthedocs.io/en/stable/walk-through/hello-world/) you can find more information on how to define the workflow.yaml.

Also take a look at the other example workflows in this folder. 

## API Endpoint

[Here](../cwr_frontend/cwr_frontend/static/openapi.yaml) is the openapi documentation of the Workflow API.

### Submit Workflow

Once you have the RO-Crate ready, you can submit the workflow.

```curl
curl --location 'baseurl/api/v1/workflows' \
--header 'Api-Key: ***' \
--form 'rocratefile=@"/path_to_file/hello-world.zip"' \
--form 'dry_run="false"' \
```

The hello-world workflow has "name" as an input parameter. In the workflow.yaml you see that by default "name" = "world". If you don't want to use the default "name", you can add the input parameter to the request like this:

```curl
curl --location 'baseurl/api/v1/workflows' \
--header 'Api-Key: ***' \
--form 'rocratefile=@"/path_to_file/hello-world.zip"' \
--form 'dry_run="false"' \
--form 'param-name="Welt"'
```
You can customize this for any parameters, by appending the parameter name to 'param-'. E.g. if the workflow had a parameter called "year", you would add param-year="2025" to the request.

This is how the response would look like. You can then use the workflow_id to check the status of the workflow in the next step.
```json
{
    "status": "Submitted",
    "workflow_id": "ba45ad7d-e887-4e5c-8a6c-4205452fc18d"
}
```

### Get Workflow Status
Now you can query the workflow status:

```curl
curl --location 'baseurl/api/v1/workflows/ba45ad7d-e887-4e5c-8a6c-4205452fc18d' \
--header 'Api-Key: ••••••'
```
Once the response tells you the workflow has finished
```json
{
    "status": "Succeeded",
    "workflow_id": "ba45ad7d-e887-4e5c-8a6c-4205452fc18d"
}
```
You can go ahead and download the results

### Download Workflow Results

```curl
curl --location 'baseurl/api/v1/workflows/ba45ad7d-e887-4e5c-8a6c-4205452fc18d/download' \
--header 'Api-Key: ••••••'
```

This will return the workflow results packaged together with the workflow description and provenance as a [Workflow-Run RO-Crate](https://www.researchobject.org/workflow-run-crate/) .