import itertools
import json
import os
import re
from unittest.mock import patch, MagicMock

import pytest
import rocrate
from rocrate_validator import services, models
from rocrate.rocrate import ROCrate
from rocrate.model import RootDataset
import tempfile

from cwr_frontend import rocrate_utils

def compare_dicts(expected, actual):
    for key in expected:
        assert key in actual
        assert expected[key] == actual[key]
    for key in actual:
        assert key in expected


def build_test_crate(json_file_name: str, detached: bool, workflow_only: bool = False) -> ROCrate:
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), json_file_name), "r"))
    remote_urls = {}

    # find root dataset id
    if len(list(filter(lambda o: "Dataset" in o["@type"], dataset_objects.values()))) == 1:
        dataset_id = next(filter(lambda o: "Dataset" in o["@type"], dataset_objects.values()))["@id"]
    else:
        for id, object in dataset_objects.items():
            if "Dataset" not in object.get("@type", []) or "isPartOf" in object:
                continue
            else:
                dataset_id = id

    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"] or "Person" in object["@type"] or "Dataset" in object["@type"]:
            remote_urls[id] = "https://example.com/" + id
        if "Dataset" in object["@type"] and "isPartOf" in object:
            for parent in object["isPartOf"]:
                remote_urls[parent] = "https://example.com/" + parent

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, detached=detached, workflow_only=workflow_only)
    return ro_crate


def validate_ro_crate_profile(ro_crate: ROCrate, profile, ignore_regex=[]):
    # ro_crate.write(tmp_dir)

    with tempfile.TemporaryDirectory() as tmp_dir:

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock(name="response")
            mock_context = MagicMock(name="context")
            mock_context.read.side_effect = itertools.cycle([b"test", None])
            mock_response.__enter__.return_value = mock_context
            mock_response.__exit__.return_value = False
            mock_urlopen.return_value = mock_response

            with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as f:
                for chunk in ro_crate.stream_zip():
                    f.write(chunk)
                f.flush()
                f.seek(0)
                import shutil
                shutil.unpack_archive(f.name, tmp_dir)
        settings = services.ValidationSettings(
            data_path=tmp_dir,
            profile_identifier=profile,
            requirement_severity=models.Severity.REQUIRED,
            abort_on_first=False
        )
        result = services.validate(settings)
        if result.has_issues():
            for issue in result.get_issues():
                # Ignore missing workflow. It cannot be found in the crate because we stream it manually in the view
                if re.search("Main Workflow .*? not found in crate", issue.message):
                    continue
                else:
                    # ignore additional regexes.
                    for regex in ignore_regex:
                        if re.search(regex, issue.message):
                            continue
                    raise AssertionError("Crate validation failed: " + str(issue))


def test_ro_crate():
    """
    Test RO crate with file based objects that does not contain a workflow.
    It should conform to Ro-Crate but not include the WRROC profile
    """
    ro_crate = build_test_crate("dataset_objects.json", detached=False)

    validate_ro_crate_profile(ro_crate, "ro-crate-1.1")

    assert len(ro_crate.get_entities()) == 5  # root_dataset, metadata, 2 files, 1 Person

    # root dataset should be ./ and has sameAs pointing to remote
    assert ro_crate.root_dataset.id == "./"
    assert ro_crate.root_dataset["sameAs"] == "https://example.com/cwr/c4e56be8890a3fda2fac"

    # Should contain actual file paths when not detached
    data_entity_ids = map(lambda e: e.id, ro_crate.data_entities)
    assert "adc9d69b-56c1-46b0-b484-f8ee86fab5a6-753409695/src/Exports/ModGP/Lathyrus/vestitus/INPUTS.png" in data_entity_ids

    # should have a link to the remote file
    for entity in ro_crate.data_entities:
        assert "sameAs" in entity

    # Make sure this crate does not use the WRROC profile
    assert ro_crate.metadata["conformsTo"] == "https://w3id.org/ro/crate/1.1"
    assert len(ro_crate.metadata.extra_contexts) == 0

    # check entities have expected properties
    dataset = ro_crate.root_dataset
    compare_dicts({
        "@id": "./",
        "@type": "Dataset",
        "datePublished": "2024-11-23T02:00:54.459Z",
        "sameAs": "https://example.com/cwr/c4e56be8890a3fda2fac",
        "hasPart": [
            {"@id": "adc9d69b-56c1-46b0-b484-f8ee86fab5a6-753409695/src/Exports/ModGP/Lathyrus/vestitus/Continuous.nc"},
            {"@id": "adc9d69b-56c1-46b0-b484-f8ee86fab5a6-753409695/src/Exports/ModGP/Lathyrus/vestitus/INPUTS.png"},
        ],
        "author": {"@id": "https://orcid.org/0000-0001-9447-460X"},
        "dateCreated": "2024-11-23T02:01:10.516Z",
        "dateModified": "2024-11-23T02:00:54.459Z",
        "description": "A test dataset",
        "keywords": ["test1", "test2"],
        "license": {"@id": "https://spdx.org/licenses/CC0-1.0"},
        "name": "Lathyrus vestitus"
    }, dataset.as_jsonld())

    # # check author
    author = ro_crate.root_dataset["author"]
    compare_dicts({
        "@id": "https://orcid.org/0000-0001-9447-460X",
        "@type": "Person",
        "name": "Daniel Bauer",
        "sameAs": {"@id": "https://example.com/cwr/94118362646bf127aabe"}
    }, author.as_jsonld())

    # # check file entity
    file1 = ro_crate.dereference("adc9d69b-56c1-46b0-b484-f8ee86fab5a6-753409695/src/Exports/ModGP/Lathyrus/vestitus/Continuous.nc")
    compare_dicts({
        "@id": "adc9d69b-56c1-46b0-b484-f8ee86fab5a6-753409695/src/Exports/ModGP/Lathyrus/vestitus/Continuous.nc",
        "@type": "File",
        "name": "Continuous.nc",
        "contentSize": 25027404,
        "encodingFormat": "application/x-netcdf",
        "contentUrl": "https://example.com/cwr/d5d6a0c4df374a22d2ab",
        "sameAs": {"@id": "https://example.com/cwr/d5d6a0c4df374a22d2ab"}
    }, file1.as_jsonld())


def test_detached_ro_crate():
    """
    Test RO crate with file based objects that does not contain a workflow.
    It should conform to Ro-Crate but not include the WRROC profile
    """
    ro_crate = build_test_crate("dataset_objects.json", detached=True)

    validate_ro_crate_profile(ro_crate, "ro-crate-1.1")

    assert len(ro_crate.get_entities()) == 5  # root_dataset, metadata, 2 files, 1 Person

    # root dataset entity should link to remote
    assert ro_crate.metadata["about"] == ro_crate.root_dataset
    assert ro_crate.root_dataset.id == "https://example.com/cwr/c4e56be8890a3fda2fac/"
    assert "sameAs" not in ro_crate.root_dataset

    # Id should link to remote file
    for entity in ro_crate.data_entities:
        assert entity.id.startswith("https://example.com/")
        assert "sameAs" not in entity

    # Make sure this crate does not use the WRROC profile
    assert ro_crate.metadata["conformsTo"] == "https://w3id.org/ro/crate/1.1"
    assert len(ro_crate.metadata.extra_contexts) == 0


def test_workflow_run_ro_crate():
    """
    Test RO crate with file based objects
    """
    ro_crate = build_test_crate("dataset_objects_workflow.json", detached=False)

    validate_ro_crate_profile(ro_crate, "workflow-run-crate-0.5")

    assert len(ro_crate.get_entities()) == 13  # root_dataset, metadata, 3 files, 8 contextual

    # root dataset should point to workflow and create action
    assert len(ro_crate.root_dataset["hasPart"]) == 3
    assert ro_crate.root_dataset["mainEntity"].id == "workflow.yaml"

    # There should be a CreateAction
    assert "CreateAction" in ro_crate.root_dataset["mentions"]["@type"]

    # Check workflow entities have expected properties
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
        "input": {"@id": "#cwr/398b64ebca54668f662d"},
        "contentUrl": "https://example.com/cwr/695601f5a098bf326246"
    }, workflow.as_jsonld())

    formal_param = workflow["input"]
    compare_dicts({
        "@id": "#cwr/398b64ebca54668f662d",
        "@type": "FormalParameter",
        "name": "text",
        "additionalType": "Text"
    }, formal_param.as_jsonld())

    action = ro_crate.root_dataset["mentions"]
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


def test_detached_workflow_run_ro_crate():
    """"
    Test RO crate with remote objects
    """
    ro_crate = build_test_crate("dataset_objects_workflow.json", detached=True)

    validate_ro_crate_profile(ro_crate, "workflow-run-crate-0.5")

    # Root dataset should be referenced by its URI instead of ./
    assert ro_crate.root_dataset.id == "https://example.com/cwr/2b408313359f2b6f18c2/"

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


def test_detached_workflow_run_ro_crate_missing_urls():
    """
    Should raise an error if a remote url to a file or dataset is missing, but not if a person url is missing
    """
    dataset_objects = json.load(open(os.path.join(os.path.dirname(__file__), "dataset_objects_workflow.json"), "r"))
    dataset_id = "cwr/2b408313359f2b6f18c2"
    remote_urls = {"cwr/2b408313359f2b6f18c2": "https://example.com/abc"}  # missing file url

    # should throw without remote urls for a file
    with pytest.raises(ValueError):
        rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, detached=True)


    remote_urls = {}
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"]:  # not for person!
            remote_urls[id] = "https://example.com/" + id
    # should throw without remote urls for a file
    with pytest.raises(ValueError):
        rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, detached=True)

    # should not throw for missing remote url for a person
    remote_urls = {"cwr/2b408313359f2b6f18c2": "https://example.com/abc"}  # missing file url
    for id, object in dataset_objects.items():
        if "MediaObject" in object["@type"]:  # not for person!
            remote_urls[id] = "https://example.com/" + id

    ro_crate = rocrate_utils.build_ROCrate(dataset_id, dataset_objects, remote_urls=remote_urls, with_preview=False, detached=True)
    assert ro_crate is not None

    author = ro_crate.root_dataset["author"]
    compare_dicts({
        "@id": "https://orcid.org/0000-0001-9447-460X",
        "@type": "Person",
        "name": "Daniel Bauer"
    }, author.as_jsonld())


def test_workflow_run_ro_crate_with_child():
    ro_crate = build_test_crate("dataset_objects_nested_crate_parent.json", detached=False)

    validate_ro_crate_profile(ro_crate, "workflow-run-crate-0.5")
    assert len(ro_crate.get_entities()) == 52

    # root dataset should list child dataset in hasPart
    child_datasets = list(filter(lambda e: "Dataset" in e["@type"] and not isinstance(e, RootDataset), ro_crate.get_entities()))
    assert len(child_datasets) == 2

    for child_dataset in child_datasets:
        assert child_dataset in filter(lambda e: e.id, ro_crate.root_dataset["hasPart"])

    # child dataset should point to remote url and conform to the ro-crate profile
    for child_dataset in child_datasets:
        assert child_dataset.id.startswith("https://example.com")
        assert "https://w3id.org/ro/crate" in child_dataset["conformsTo"]


def test_ro_crate_with_parent():
    ro_crate = build_test_crate("dataset_objects_nested_crate_child.json", detached=False)

    validate_ro_crate_profile(ro_crate, "ro-crate-1.1")
    assert len(ro_crate.get_entities()) == 18

    assert "https://example.com/cwr/391c48d5cc201aa5e445" in ro_crate.root_dataset["isPartOf"]


def test_detached_workflow_run_ro_crate_with_child():
    """ Should correctly reference the child urls """
    ro_crate = build_test_crate("dataset_objects_nested_crate_parent.json", detached=True)

    validate_ro_crate_profile(ro_crate, "workflow-run-crate-0.5")
    assert len(ro_crate.get_entities()) == 52

    # root dataset should list child dataset in hasPart
    child_datasets = list(filter(lambda e: "Dataset" in e["@type"] and not isinstance(e, RootDataset), ro_crate.get_entities()))
    assert len(child_datasets) == 2

    for child_dataset in child_datasets:
        assert child_dataset in filter(lambda e: e.id, ro_crate.root_dataset["hasPart"])

    # child dataset should point to remote url and conform to the ro-crate profile
    for child_dataset in child_datasets:
        assert child_dataset.id.startswith("https://example.com")
        assert "https://w3id.org/ro/crate" in child_dataset["conformsTo"]



def test_detached_ro_crate_with_parent():
    ro_crate = build_test_crate("dataset_objects_nested_crate_child.json", detached=True)

    validate_ro_crate_profile(ro_crate, "ro-crate-1.1")
    assert len(ro_crate.get_entities()) == 18

    assert "https://example.com/cwr/391c48d5cc201aa5e445" in ro_crate.root_dataset["isPartOf"]

def test_workflow_ro_crate_without_workflow():
    """
    Should fail. A dataset without workflow cannot be built into a workflow ro-crate
    """
    with pytest.raises(ValueError):
        build_test_crate("dataset_objects.json", detached=False, workflow_only=True)

def test_workflow_ro_crate():
    """
    Should only return the workflow and filter other entity
    """
    ro_crate = build_test_crate("dataset_objects_workflow.json", detached=False, workflow_only=True)

    validate_ro_crate_profile(ro_crate, "workflow-ro-crate-1.0")
    assert len(ro_crate.get_entities()) == 6  # root_dataset, metadata, workflow file, computer language, parameter, author

    # root dataset should point to workflow
    assert isinstance(ro_crate.root_dataset["hasPart"], rocrate.model.File)
    assert ro_crate.root_dataset["mainEntity"].id == "workflow.yaml"

    # Create Action should have been filtered out
    assert "mentions" not in ro_crate.root_dataset

    # Check workflow entities have expected properties
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
        "input": {"@id": "#cwr/398b64ebca54668f662d"},
        "contentUrl": "https://example.com/cwr/695601f5a098bf326246"
    }, workflow.as_jsonld())

    formal_param = workflow["input"]
    compare_dicts({
        "@id": "#cwr/398b64ebca54668f662d",
        "@type": "FormalParameter",
        "name": "text",
        "additionalType": "Text",
    }, formal_param.as_jsonld())