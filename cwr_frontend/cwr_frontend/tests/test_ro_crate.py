import json
import os
import re

import pytest
from rocrate_validator import services, models
import tempfile

from cwr_frontend import rocrate_utils

def compare_dicts(expected, actual):
    for key in expected:
        assert key in actual
        assert expected[key] == actual[key]
    for key in actual:
        assert key in expected

def test_remote_ro_crate():
    """"
    Test RO crate with remote objects
    """
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), "dataset_objects_workflow.json"), "r"))
    dataset_id = "cwr/2b408313359f2b6f18c2"
    remote_urls = {}
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"] or "Person" in object["@type"]:
            remote_urls[id] = "https://example.com/" + id

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, download=False)

    with tempfile.TemporaryDirectory() as tmp_dir:
        ro_crate.write(tmp_dir)
        settings = services.ValidationSettings(
            data_path=tmp_dir,
            profile_identifier="workflow-run-crate-0.5",
            requirement_severity=models.Severity.REQUIRED,
            abort_on_first=False
        )
        result = services.validate(settings)
        if result.has_issues():
            for issue in result.get_issues():
                # Ignore missing workflow. It can't be found because it is an empty example crate.
                if re.search("Main Workflow .*? not found in crate", issue.message):
                    continue
                else:
                    raise AssertionError("Crate validation failed: " + str(issue))

    assert ro_crate.root_dataset["@id"] == "./"

    assert ro_crate.dereference("https://orcid.org/0000-0001-9447-460X") is not None
    assert ro_crate.dereference("https://example.com/cwr/695601f5a098bf326246") is not None
    assert ro_crate.dereference("https://example.com/cwr/0d6b270d30e33a451e64") is not None
    assert ro_crate.dereference("https://example.com/cwr/00ff7fa98ac0694e0f20") is not None

    assert ro_crate.root_dataset["mainEntity"]["@id"] == "https://example.com/cwr/695601f5a098bf326246"
    assert [entity["@id"] for entity in ro_crate.root_dataset["hasPart"]] == [
        "https://example.com/cwr/0d6b270d30e33a451e64",
        "https://example.com/cwr/00ff7fa98ac0694e0f20",
        "https://example.com/cwr/695601f5a098bf326246",
    ]
    assert ro_crate.root_dataset["mentions"]["@id"].startswith("#cwr")

    action = ro_crate.root_dataset["mentions"]
    assert action["instrument"]["@id"] == "https://example.com/cwr/695601f5a098bf326246"
    assert action["agent"]["@id"] == "https://orcid.org/0000-0001-9447-460X"
    assert [entity["@id"] for entity in action["result"]] == [
        "https://example.com/cwr/0d6b270d30e33a451e64",
        "https://example.com/cwr/00ff7fa98ac0694e0f20",
    ]


def test_remote_ro_crate_missing_urls():
    """
    Should raise an error if a remote url to a file is missing, but not if a person url is missing
    """
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), "dataset_objects_workflow.json"), "r"))
    dataset_id = "cwr/2b408313359f2b6f18c2"
    remote_urls = {}

    # should throw without remote urls for a file
    with pytest.raises(ValueError):
        rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, download=False)

    # should not throw for missing remote url for a person
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"]:  # not for person!
            remote_urls[id] = "https://example.com/" + id

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, download=False)
    assert ro_crate is not None

    author = ro_crate.root_dataset["author"]
    compare_dicts({
        "@id": "https://orcid.org/0000-0001-9447-460X",
        "@type": "Person",
        "name": "Daniel Bauer"
    }, author.as_jsonld())


def test_file_based_ro_crate():
    """
    Test RO crate with file based objects
    """
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), "dataset_objects_workflow.json"), "r"))
    dataset_id = "cwr/2b408313359f2b6f18c2"
    remote_urls = {}
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"] or "Person" in object["@type"]:
            remote_urls[id] = "https://example.com/" + id

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, download=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        ro_crate.write(tmp_dir)
        settings = services.ValidationSettings(
            data_path=tmp_dir,
            profile_identifier="workflow-run-crate-0.5",
            requirement_severity=models.Severity.REQUIRED,
            abort_on_first=False
        )
        result = services.validate(settings)
        if result.has_issues():
            for issue in result.get_issues():
                # Ignore missing workflow. It can't be found because it is an empty example crate.
                if re.search("Main Workflow .*? not found in crate", issue.message):
                    continue
                else:
                    raise AssertionError("Crate validation failed: " + str(issue))

    assert len(ro_crate.get_entities()) == 13  # root_dataset, metadata, 3 files, 8 contextual

    # check dataset
    dataset = ro_crate.root_dataset
    compare_dicts({
        "@id": "./",
        "@type": "Dataset",
        "datePublished": "2024-08-13T08:58:38.161Z",
        "hasPart": [
            {"@id": "91c23560-7799-406d-bc3f-95d62e722154/testfile.txt"},
            {"@id": "91c23560-7799-406d-bc3f-95d62e722154/main.log"},
            {"@id": "workflow.yaml"}
        ],
        "author": {"@id": "https://orcid.org/0000-0001-9447-460X"},
        "dateCreated": "2024-08-13T08:58:38.161Z",
        "dateModified": "2024-08-13T08:58:38.161Z",
        "description": "A test dataset from an argo workflow submitted via the Frontend as RO-Crate",
        "keywords": ["test", "test2"],
        "license": {"@id": "https://spdx.org/licenses/CC-BY-SA-4.0"},
        "mainEntity": {"@id": "workflow.yaml"},
        "mentions": {"@id": "#cwr/de5f500051a7541fbc2e"},
        "name": "Test Dataset",
        "conformsTo": [
            {"@id": "https://w3id.org/ro/wfrun/process/0.5"},
            {"@id": "https://w3id.org/ro/wfrun/workflow/0.5"},
            {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"}
        ]
    }, dataset.as_jsonld())

    # check author
    author = ro_crate.root_dataset["author"]
    compare_dicts({
        "@id": "https://orcid.org/0000-0001-9447-460X",
        "@type": "Person",
        "name": "Daniel Bauer",
        "sameAs": {"@id": "https://example.com/cwr/cfa5c956a2bd56ec6554"}
    }, author.as_jsonld())

    # check file entity
    file1 = ro_crate.dereference("91c23560-7799-406d-bc3f-95d62e722154/testfile.txt")
    compare_dicts({
        "@id": "91c23560-7799-406d-bc3f-95d62e722154/testfile.txt",
        "@type": "File",
        "name": "testfile.txt",
        "contentSize": 129,
        "encodingFormat": "application/gzip",
        "sameAs": {"@id": "https://example.com/cwr/0d6b270d30e33a451e64"}
    }, file1.as_jsonld())

    workflow = ro_crate.dereference("workflow.yaml")
    compare_dicts({
        "@id": "workflow.yaml",
        "@type": ["File", "ComputationalWorkflow", "SoftwareSourceCode"],
        "name": "workflow.yaml",
        "description": "Argo workflow definition",
        "sameAs": {"@id": "https://example.com/cwr/695601f5a098bf326246"},
        "programmingLanguage": {"@id": "https://argoproj.github.io/workflows"},
        "contentSize": 2034,
        "encodingFormat": "text/yaml",
        "input": {"@id": "#cwr/398b64ebca54668f662d"}
    }, workflow.as_jsonld())

    formal_param = workflow["input"]
    compare_dicts({
        "@id": "#cwr/398b64ebca54668f662d",
        "@type": "FormalParameter",
        "name": "text",
        "additionalType": "Text"
    }, formal_param.as_jsonld())

    action = dataset["mentions"]
    compare_dicts({
        "@id": "#cwr/de5f500051a7541fbc2e",
        "@type": "CreateAction",
        "agent": {"@id": "https://orcid.org/0000-0001-9447-460X"},
        "startTime": "2024-08-13T08:58:22Z",
        "endTime": "2024-08-13T08:58:27Z",
        "object": {"@id": "#cwr/5022e06049869532d773"},
        "instrument": {"@id": "workflow.yaml"},
        "result": [
            {"@id": "91c23560-7799-406d-bc3f-95d62e722154/testfile.txt"},
            {"@id": "91c23560-7799-406d-bc3f-95d62e722154/main.log"}
        ]
    }, action.as_jsonld())

    action_property = action["object"]
    compare_dicts({
        "@id": "#cwr/5022e06049869532d773",
        "@type": "PropertyValue",
        "name": "text",
        "value": "test parameter"
    }, action_property.as_jsonld())

def test_ro_crate_without_workflow():

    """
    Test RO crate with file based objects that does not contain a workflow.
    It should conform to Ro-Crate but not include the WRROC profile
    """
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), "dataset_objects.json"), "r"))
    dataset_id = "cwr/c4e56be8890a3fda2fac"
    remote_urls = {"cwr/d1d35fd05b740bb3c393": "https://example.com/cwr/d1d35fd05b740bb3c393?format=ROCrate"}
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"] or "Person" in object["@type"]:
            remote_urls[id] = "https://example.com/" + id

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, download=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        ro_crate.write(tmp_dir)
        settings = services.ValidationSettings(
            data_path=tmp_dir,
            profile_identifier="ro-crate-1.1",
            requirement_severity=models.Severity.REQUIRED,
            abort_on_first=False
        )
        result = services.validate(settings)
        if result.has_issues():
            for issue in result.get_issues():
                # Ignore missing workflow. It can't be found because it is an empty example crate.
                if re.search("Main Workflow .*? not found in crate", issue.message):
                    continue
                else:
                    raise AssertionError("Crate validation failed: " + str(issue))

    assert len(ro_crate.get_entities()) == 17  # root_dataset, metadata, 14 files, 1 Person

    # Make sure this crate does not use the WRROC profile
    assert ro_crate.metadata["conformsTo"] == "https://w3id.org/ro/crate/1.1"
    assert len(ro_crate.metadata.extra_contexts) == 0

    # Make sure this crate references its parents crate for provenance
    assert "isPartOf" in ro_crate.root_dataset
    assert ro_crate.root_dataset["isPartOf"] == "https://example.com/cwr/d1d35fd05b740bb3c393?format=ROCrate"