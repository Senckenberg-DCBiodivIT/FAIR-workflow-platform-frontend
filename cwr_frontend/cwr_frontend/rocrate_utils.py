from copy import deepcopy
from typing import Any

from rocrate.model import Person, ContextEntity, Dataset

from cwr_frontend.jsonld_utils import pyld_caching_document_loader
from pyld import jsonld
from rocrate.rocrate import ROCrate
from cwr_frontend.jsonld_utils import replace_values


def build_ROCrate(dataset_id: str, objects: dict[str, dict[str, Any]], remote_urls: dict[str, str],
                  with_preview: bool = False, download: bool = False) -> ROCrate:
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

    jsonld.set_document_loader(pyld_caching_document_loader)
    flattened = jsonld.flatten(list(objects.values()), ["https://w3id.org/ro/crate/1.1/context",
                                                        "https://www.researchobject.org/ro-terms/workflow-run/context.jsonld"])

    id_map = {}  # map of CorA
    # dra internal ids to created RO-Crate ids

    crate = ROCrate(gen_preview=with_preview)

    for object in flattened["@graph"]:
        # skip root entity
        if object["@id"] == dataset_id:
            continue

        # pop id from object, otherwise it will overwrite identifiers (i.e. for Person and File)
        cordra_id = object.pop("@id")

        # Is there a remote URL for this object?
        remote_url = remote_urls.get(cordra_id, None) if remote_urls else None
        if remote_url:
            object["sameAs"] = {"@id": remote_url}

        if object["@type"] == "Person":
            # For person, we want to use their identifier (ORCID) as id if present, and set their sameAs to the remote URL
            identifier = object.pop("identifier") if "identifier" in object else cordra_id
            if remote_url:
                object["sameAs"] = {"@id": remote_url}

            crate_obj = crate.add(Person(crate, identifier, object))
            id_map[cordra_id] = crate_obj.id
        elif object["@type"] == "File" or (isinstance(object["@type"], list) and "File" in object["@type"]):
            # For files, it depends on whether this will be a remote RO-Crate or the user requested a download
            # For remote, we want to use the remote URL to the payload as ID
            # For download, we want to use the file path in the crate
            if not download:
                dest_path = None  # no file download url => remote file
                if "sameAs" in object:
                    del object["sameAs"]
            else:
                dest_path = object["contentUrl"]["@id"]
            # remove internally used keys
            for key in ["contentUrl", "isPartOf", "partOf", "resultOf"]:
                if key in object:
                    del object[key]

            crate_obj = crate.add_file(remote_url, dest_path=dest_path, fetch_remote=False, properties=object)
            id_map[cordra_id] = crate_obj.id
        elif object["@type"] == "Dataset":
            # TODO integration of nested datasets has some issues with the download option set:
            # - files are placed relative to the root dataset. Therefore, if two datasets contain a file under the same path, only one file will be present
            # Instead, we could place datasets in subfolders (foldername = cordra id?) and rewrite the file path
            # However, this would require some refactoring to rewrite file paths based on what dataset reference them
            # Alternatively, we could opt to not include the files from nested datasets in the final crate, but only reference their URL:
            # https://www.researchobject.org/ro-crate/specification/1.1/data-entities.html#directories-on-the-web-dataset-distributions
            for key, value in object.items():
                if isinstance(value, dict) and "@value" in value:  # fix for https://github.com/ResearchObject/ro-crate-py/issues/190
                    object[key] = value["@value"]
            crate_obj = crate.add(ContextEntity(crate, cordra_id, properties=object))
            id_map[cordra_id] = crate_obj.id
        else:
            # Everything else is added as a ContextEntity, where we use the identifier if present,
            # and the cordra_id if not
            identifier = object.pop("identifier") if "identifier" in object else cordra_id
            crate_obj = crate.add(ContextEntity(crate, identifier, object))
            id_map[cordra_id] = crate_obj.id

    # Add attributes to dataset entity
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
        # make this a valid workflow run RO-Crate
        crate.metadata.extra_contexts.append("https://w3id.org/ro/terms/workflow-run/context")
        crate.metadata["conformsTo"] = [
            {"@id": "https://w3id.org/ro/crate/1.1"},
            {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"}
        ]
        for profile in ["https://w3id.org/ro/wfrun/process/0.5", "https://w3id.org/ro/wfrun/workflow/0.5", "https://w3id.org/workflowhub/workflow-ro-crate/1.0"]:
            profile_entity = crate.add(ContextEntity(crate, profile, properties={
                "@type": "CreativeWork",
                "version": profile.split("/")[-1],
            }))
            crate.root_dataset.append_to("conformsTo", profile_entity)

    return crate
