import io
import json
import os.path
from copy import deepcopy
from typing import Any, Generator
from zipfile import ZipFile, ZIP_DEFLATED
import requests
import rocrate.model

from rocrate.model import Person, ContextEntity, Dataset

from cwr_frontend.jsonld_utils import pyld_caching_document_loader
from pyld import jsonld
from rocrate.rocrate import ROCrate
from rocrate.model import RootDataset
from cwr_frontend.jsonld_utils import replace_values


def _remove_children_from_objects(objects, child_id):
    if objects[child_id]["@type"] == "Dataset" or (isinstance(objects[child_id]["@type"], list) and "Dataset" in objects[child_id]["@type"]):
        for grandchild_id in objects[child_id]["hasPart"]:
            _remove_children_from_objects(objects, grandchild_id)
    objects.pop(child_id, None)

def _filter_objects_for_workflow_crate(objects: dict[str, dict[str, Any]], dataset_id: str) -> dict[str, dict[str, Any]]:
    workflow_id = objects[dataset_id].get("mainEntity", None)
    if not workflow_id:
        raise ValueError("No mainEntity found in dataset")

    for file_id in objects[dataset_id]["hasPart"]:
        if file_id != workflow_id:
            _remove_children_from_objects(objects, file_id)

    objects[dataset_id]["hasPart"] = [workflow_id]
    for mention in objects[dataset_id].get("mentions", []):
        for action_related_object in objects[mention].get("object", []) + objects[mention].get("result", []):
            objects.pop(action_related_object, None)
        objects.pop(mention, None)
    del objects[dataset_id]["mentions"]

def build_ROCrate(dataset_id: str, objects: dict[str, dict[str, Any]], remote_urls: dict[str, str],
                  with_preview: bool = False, detached: bool = False, workflow_only: bool = False) -> ROCrate:
    objects = deepcopy(objects)  # make sure to not leak edits out of this method

    # For all objects, we first want to flatten the JSONLD to the RO Crate context
    # This will remove our custom contexts and the type coercion
    # Since RO-Crate uses http://schema.org and not https://schema.org, we need to replace this manually.
    # Objects are then put in a graph so that flattening is a single operations (and pyld reuses the remote context)

    # add all objects to the crate.
    # flatten them to the appropriate context of RO-Crate and Workflow run RO Crates.
    for object in objects.values():
        # hotfix for Cordra using https instead of http for schemas, while RO-Crates use http
        if "@context" in object:
            object["@context"] = replace_values(object, {r"https://schema\.org(.*)": r"http://schema.org\1"})

    if workflow_only:
        _filter_objects_for_workflow_crate(objects, dataset_id)

    jsonld.set_document_loader(pyld_caching_document_loader)
    flattened = jsonld.flatten(list(objects.values()), ["https://w3id.org/ro/crate/1.1/context",
                                                        "https://www.researchobject.org/ro-terms/workflow-run/context.jsonld"])

    id_map = {}  # map of CorA
    # map internal ids to created RO-Crate ids

    crate = ROCrate(gen_preview=with_preview)

    if detached:
        if not dataset_id in remote_urls:
            raise ValueError("Missing remote url for root dataset entity")
        # replace id of root dataset in detached crate (see https://github.com/ResearchObject/ro-crate-py/issues/206)
        _original_root = crate.root_dataset
        crate.add(RootDataset(crate, remote_urls[dataset_id]))
        crate.metadata["about"] = crate.root_dataset
        crate.delete(_original_root)
    elif dataset_id in remote_urls:
        # set sameAs on root dataset
        crate.root_dataset["sameAs"] = remote_urls[dataset_id]

    for object in flattened["@graph"]:
        # skip root entity
        if object["@id"] == dataset_id:
            continue

        # pop id from object, otherwise it will overwrite identifiers (i.e. for Person and File)
        cordra_id = object.pop("@id")

        # add remote url to crate files if not detached
        remote_url = remote_urls.get(cordra_id, None) if remote_urls else None
        if remote_url and not detached:
            object["sameAs"] = {"@id": remote_url}

        if object["@type"] == "Person":
            # For person, we want to use their identifier (ORCID) as id if present, and set their sameAs to the remote URL
            identifier = object.pop("identifier") if "identifier" in object else cordra_id

            crate_obj = crate.add(Person(crate, identifier, object))
            id_map[cordra_id] = crate_obj.id
        elif object["@type"] == "File" or (isinstance(object["@type"], list) and "File" in object["@type"]):
            if detached:
                dest_path = None
            else:
                dest_path = object["contentUrl"]["@id"]

            # remove internally used keys
            for key in ["contentUrl", "isPartOf", "partOf", "resultOf"]:
                if key in object:
                    del object[key]

            crate_obj = crate.add_file(remote_url, dest_path=dest_path, fetch_remote=not detached, properties=object)
            id_map[cordra_id] = crate_obj.id
        elif object["@type"] == "Dataset":
            # Referencing remote RO-Crates: https://www.researchobject.org/ro-crate/specification/1.2-DRAFT/data-entities.html#referencing-other-ro-crates

            for key, value in object.items():
                if isinstance(value, dict) and "@value" in value:  # fix for https://github.com/ResearchObject/ro-crate-py/issues/190
                    object[key] = value["@value"]

            # remove internally used keys
            for key in ["contentUrl", "isPartOf", "partOf", "resultOf"]:
                if key in object:
                    del object[key]

            # make ro-crate-py / validator happy.
            if not remote_url.endswith("/"):
                remote_url += "/"

            crate_obj = crate.add_file(remote_url, fetch_remote=False, properties=object)
            crate_obj.append_to("conformsTo", {"@id": "https://w3id.org/ro/crate"})
            id_map[cordra_id] = crate_obj.id
        else:
            # Everything else is added as a ContextEntity, where we use the identifier if present,
            # and the cordra_id if not
            identifier = object.pop("identifier") if "identifier" in object else cordra_id
            crate_obj = crate.add(ContextEntity(crate, identifier, object))
            id_map[cordra_id] = crate_obj.id

    # Add attributes to root dataset entity
    dataset = next(filter(lambda o: "@id" in o and o["@id"] == dataset_id, flattened["@graph"]))
    for key, value in dataset.items():
        if key == "@context" or key == "@id" or key == "@type": continue
        if key == "isPartOf":
            value = {"@id": remote_urls[value["@id"]]}
        if isinstance(value, dict) and "@value" in value:  # fix for https://github.com/ResearchObject/ro-crate-py/issues/190
            value = value["@value"]
        crate.root_dataset[key] = replace_values(value, id_map)

    # nested crates don't always have a description (ModGP), so we use their name to make a valid crate
    if not "description" in crate.root_dataset:
        crate.root_dataset["description"] = crate.root_dataset["name"]

    # Replace corda IDs with RO-Crate IDs
    for entity in crate.get_entities():
        for key in entity:
            if key in ["@type", "@id", "@context"]: continue
            replaced = replace_values(entity.as_jsonld()[key], id_map)
            if replaced != entity[key]:
                # The RO-Crate rewrited {"@id": xxx} to xxx if the id is not present in the crate yet.
                # We undo that here when replacing internal ids with RO-Crate ids
                if isinstance(replaced, str):
                    replaced = {"@id": replaced}
                elif isinstance(replaced, list) and len(replaced) > 0 and "@id" not in replaced[0]:
                    replaced = [{"@id": entity_id} for entity_id in replaced]
            entity[key] = replaced

    if "mainEntity" in crate.root_dataset:
        # make this a valid Workflow RO-Crate
        crate.metadata.extra_contexts.append("https://w3id.org/ro/terms/workflow-run/context")
        crate.metadata["conformsTo"] = [
            {"@id": "https://w3id.org/ro/crate/1.1"},
            {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"}
        ]
        if "mentions" in crate.root_dataset:
            # make this a valid Workflow Run RO-Crate
            for profile in ["https://w3id.org/ro/wfrun/process/0.5", "https://w3id.org/ro/wfrun/workflow/0.5", "https://w3id.org/workflowhub/workflow-ro-crate/1.0"]:
                profile_entity = crate.add(ContextEntity(crate, profile, properties={
                    "@type": "CreativeWork",
                    "version": profile.split("/")[-1],
                }))
                crate.root_dataset.append_to("conformsTo", profile_entity)

    return crate

def stream_ROCrate(crate: ROCrate) -> Generator[bytes, None, None]:
    """ Streams the content of an ROCrate into a ZIP archive.

    This function creates the zip archive in memory and streams its content in chunks.
    It handles metadata, preview HTML files, and associated file entities, fetching remote file content as needed.
    For remote content, the data is streamed directly to the output to reduce memory usage.
    No temporary files are allocated. Makes sure only a single file is streamed at once
    """
    class MemoryBuffer(io.RawIOBase):
        def __init__(self):
            self._buffer = b""

        def writable(self):
            return True

        def write(self, b):
            if self.closed:
                raise RuntimeError("Stream war closed before writing!")
            self._buffer += b
            return len(b)

        def read(self):
            chunk = self._buffer
            self._buffer = b""
            return chunk

    buffer = MemoryBuffer()
    with requests.session() as session:
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            # Write ro-crate-metadata.json to zip stream
            archive.writestr(crate.metadata.id, json.dumps(crate.metadata.generate(), indent=4))
            yield buffer.read()

            # Write preview html
            for preview in filter(lambda e: isinstance(e, rocrate.model.Preview), crate.get_entities()):
                archive.writestr(preview.id, preview.generate_html())
                yield buffer.read()

            # Iterate files, fetch their content from remote and write them to the stream
            for file_entity in crate.get_by_type("File"):
                file_path = file_entity.id
                if isinstance(file_entity.source, str):
                    if file_entity.source.startswith("http"):
                        if not file_entity.fetch_remote:
                            continue
                        response = session.get(file_entity.source, verify=False, stream=True)
                        response.raise_for_status()
                        with archive.open(file_path, mode="w") as file:
                            for chunk in response.iter_content(chunk_size=1024):
                                file.write(chunk)
                                yield buffer.read()
                    else:
                        if not os.path.exists(file_entity.source):
                            raise FileNotFoundError(file_entity.source)
                        with open(file_entity.source, "rb") as in_file, archive.open(file_path, mode="w") as file:
                            for chunk in in_file:
                                file.write(chunk)
                                yield buffer.read()
                elif isinstance(file_entity.source, io.IOBase):
                    with archive.open(file_path, mode="w") as file:
                        read = file_entity.source.read()
                        while len(read) > 0:
                            if isinstance(read, str):
                                file.write(str.encode(read))
                            else:
                                file.write(read)
                            read = file_entity.source.read()
                            yield buffer.read()
                else:
                    raise ValueError(f"Unsupported file source type: {type(file_entity.source)}")

    # ensure stream is read completely
    yield buffer.read()
    buffer.close()
