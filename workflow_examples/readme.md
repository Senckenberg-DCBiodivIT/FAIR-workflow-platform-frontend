# Workflow API Usage

## Prepare RO-Crate

The RO-Crate is a zip folder and must contain at least two files: "ro-crate-metadata.json" and "workflow.yaml".

### Metadata Description

The `ro-crate-metadata.json` needs to follow the [Workflow RO-Crate](https://about.workflowhub.eu/Workflow-RO-Crate/) profile. You can use the [Hello World example](hello-world/ro-crate-metadata.json) or the [template](ro-crate-metadata-template.json) to get started.

When adapting the template to your own workflow, you will need to update the following sections:

#### 1. Root Dataset (`@id = "./"`)
This represents your workflow as a dataset. Update these fields to match your workflow:

| Field         | Description                                                 |
| ------------- | ----------------------------------------------------------- |
| `name`        | The title of your workflow.                                 |
| `description` | A short description of what your workflow does.             |
| `keywords`    | List of keywords.                                           |
| `license`     | SPDX license URL (e.g., `"https://spdx.org/licenses/MIT"`). |

**Example:**


```json
{
      "@id": "./",
      "@type": "Dataset",
      "name": "Hello World Workflow Example",
      "description": "An example Argo workflow that prints 'Hello World' into a text file.",
      "keywords": [
        "Hello World",
        "Example",
        "Argo Workflow",
      ],
      "license": {
        "@id": "https://spdx.org/licenses/MIT"
      },
      "hasPart": [
        {
          "@id": "workflow.yaml"
        }
      ],
      "mainEntity": {
        "@id": "workflow.yaml"
      },
      "conformsTo": [
        {
          "@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"
        },
        {
          "@id": "https://w3id.org/ro/wfrun/process/0.5"
        },
        {
          "@id": "https://w3id.org/ro/wfrun/workflow/0.5"
        }
      ]
    }
```

#### 2. Input Parameters

If your workflow is parameterized, define FormalParameter entries for each input. These describe what inputs are expected, not the actual input values (which are provided when the workflow is submitted).

**Example:**

```json
{
  "@id": "#input_name",
  "@type": "FormalParameter",
  "additionalType": "Text",
  "name": "name",
  "description": "Name of the person to greet in the Hello World message",
  "valueRequired": "true",
  "defaultValue": "Anton"
}
```
Required fields:

- name and description
- @id: Unique identifier for the input parameter.
- additionalType: Data type (Text, Int, Boolean, etc.).
- valueRequired: "true" if the input must be provided.

Optional fields:
- defaultValue: default Value used, when no value provided.

#### 3. Workflow File Metadata

Reference input parameters in the ComputationalWorkflow entry and provide a description of the workflow file.

**Example:**

```json
{
  "@id": "workflow.yaml",
  "@type": ["File", "ComputationalWorkflow", "SoftwareSourceCode"],
  "name": "workflow.yaml",
  "description": "Argo workflow YAML file that prints a greeting to a text file",
  "encodingFormat": "text/yaml",
  "input": [{ "@id": "#input_name" }],
  "programmingLanguage": { "@id": "https://argoproj.github.io/workflows" }
}

```


### Workflow YAML

Once your ro-crate-metadata.json is prepared, you need to provide the actual workflow YAML file that implements the workflow logic. This YAML file defines the steps, input parameters, and outputs (artifacts or parameters) for your workflow.

You can use the [Hello world example](hello-world/workflow.yaml) or the [workflow template](workflow-template.yaml) as a starting point. And [here](https://argo-workflows.readthedocs.io/en/stable/walk-through/hello-world/) you can find more information on how to define the workflow.yaml.

Below is a step-by-step guide for creating a 2-step workflow YAML based on the Hello World example.

#### 1. Workflow Metadata
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: hello-world-
spec:
  arguments:
    parameters:
    - name: name
      description: Name of the person to greet
      value: World

  artifactGC:
    forceFinalizerRemoval: true
  podGC:
    strategy: OnWorkflowSuccess

  entrypoint: main-workflow
```
- `generateName`: prefix for workflow run names.
- `arguments.parameters`: define workflow-level inputs with a name, description, and default value.
- `entrypoint`: points to the main workflow template that sequences steps.

#### 2. Main Workflow Template
```yaml
- name: main-workflow
    steps:
    - - name: generate-greeting
        template: step1-script
        arguments:
          parameters:
          - name: name
            value: '{{workflow.parameters.name}}'
    - - name: summarize-greeting
        template: step2-container
        arguments:
          parameters:
          - name: greeting
            value: '{{steps.generate-greeting.outputs.parameters.greeting}}'

```
- Each step references a template that defines what to run.
- In Argo Workflows, `{{ }}` is used to reference variables dynamically. Use  `{{workflow.parameters.<name>}}` to access workflow-level inputs, `{{steps.<step>.outputs.parameters.<name>}}` for output parameters from previous steps, and `{{steps.<step>.outputs.artifacts.<name>}}` for files produced by previous steps. This allows data to flow between steps and templates seamlessly.
- Steps are executed sequentially by default.

#### 3. Step 1: Script Step (produces a parameter)

```yaml
  - name: step1-script
    inputs:
      parameters:
      - name: name
    outputs:
      parameters:
      - name: greeting
        valueFrom:
          path: /tmp/greeting.txt
    script:
      image: python:3.9
      command: ["python"]
      source: |
        name = "{{inputs.parameters.name}}"
        greeting = f"Hello, {name}!"
        
        # Write greeting to the parameter file
        with open("/tmp/greeting.txt", "w") as f:
            f.write(greeting)
```


Notes:

- Script steps must write output parameters to a file that matches valueFrom.path.
- Use this step for small outputs (strings, numbers, etc.).
- You can also produce artifacts (files) here if needed.

#### 4. Step 2: Container Step (produces an artifact)
```yaml
  - name: step2-container
    inputs:
      parameters:
      - name: greeting  
    outputs:
      artifacts:
      - name: summary-file
        path: /tmp/summary.txt
        archive:
          none: {}
    container:
      name: summarize-container
      image: alpine
      command: ["/bin/sh", "-c"]
      args:
      - |
        echo "Greeting: {{inputs.parameters.greeting}}" > /tmp/summary.txt
        echo "Saved summary to /tmp/summary.txt"

```

Notes:

- Container steps are ideal for running prebuilt customized images.
- Use input parameters to consume outputs from previous steps.
- Use artifacts to persist files that can be consumed by later steps or downloaded.

## API Endpoint

The API documentation of the Workflow API can be retrieved at localhost:${FRONTEND_PORT}/api/v1/docs.

### Submit Workflow

Once you have the RO-Crate ready, you can submit the workflow.

```curl
curl --location 'baseurl/api/v1/workflows' \
--header 'Api-Key: ***' \
--form 'rocratefile=@"/path_to_file/hello-world.zip"' \
--form 'dry_run="false"' \
--form 'webhook_url="xxx"'\
```
If you provide a webhook url, it will be triggered once the workflow execution completed.
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
If you have not provided a webhook url upon workflow submission, you can instead query the workflow status:

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