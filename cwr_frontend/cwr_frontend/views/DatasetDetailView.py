import json
import tempfile
from datetime import datetime
from typing import Any

import requests
import zipstream
from django.http import JsonResponse, HttpResponseBase, StreamingHttpResponse, Http404
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import TemplateView
from django_signposting.utils import add_signposts
from requests import HTTPError
from rocrate.model import ContextEntity, Person
from rocrate.rocrate import ROCrate

from cwr_frontend.cordra.CordraConnector import CordraConnector


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"
    _connector = CordraConnector()

    def render(self, request, id: str, objects: dict[str, dict[str, Any]]):
        """ Return a html representation with signposts from the given digital object """
        dataset = objects[id]

        # tuples of author names and identifiers
        authors = [(elem["name"], elem.get("identifier")) for (elem_id, elem) in objects.items() if
                            "Person" in elem["@type"] and elem_id in dataset["author"]]

        license_id = dataset["license"] if "license" in dataset else None

        link_rocrate = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=ROCrate"
        link_digital_object = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=json"

        prov_action = next(iter(elem for (key, elem) in objects.items() if "CreateAction" in elem["@type"]), None)
        if prov_action is not None:

            prov_agent_internal_id = prov_action.get("agent")
            prov_start_time = prov_action.get("startTime", None)
            prov_end_time = prov_action.get("endTime", None)

            prov_agent = next(iter(elem for (key, elem) in objects.items() if elem["@id"] == prov_agent_internal_id), None)
            prov_agent_id = prov_agent.get("identifier")
            prov_agent_name = prov_agent.get("name")

            parameters = [(elem.get("name"), elem.get("value")) for (key, elem) in objects.items() if elem["@id"] in prov_action.get("object", [])]

            prov_instrument_internal_id = prov_action.get("instrument")
            prov_instrument = {}
            if prov_instrument_internal_id is not None:
                prov_instrument = next(iter(elem for (key, elem) in objects.items() if elem["@id"] == prov_instrument_internal_id and prov_instrument_internal_id is not None), None)
                prov_instrument["name"] = prov_instrument.get("name", prov_instrument.get("contentUrl"))
                prov_instrument["description"] = prov_instrument.get("description")
                if "SoftwareApplication" in prov_instrument["@type"]:
                    prov_instrument["url"] = prov_instrument.get("identifier")
                elif "ComputationalWorkflow" in prov_instrument["@type"]:
                    prov_instrument["url"] = self._connector.get_object_abs_url(prov_instrument_internal_id, prov_instrument["contentUrl"])
                    prov_instrument["programmingLanguage"] = prov_instrument.get("programmingLanguage")

            prov_context = {
                "agent_id": prov_agent_id,
                "agent_name": prov_agent_name,
                "instrument": prov_instrument,
                "start_time": datetime.strptime(prov_start_time, "%Y-%m-%dT%H:%M:%SZ") if prov_start_time is not None else None,
                "end_time": datetime.strptime(prov_end_time, "%Y-%m-%dT%H:%M:%SZ") if prov_end_time is not None else None,
                "parameters": parameters
            }
        else:
            prov_context = None

        # render content
        context = {
            "id": id,
            "name": dataset["name"],
            "description": dataset["description"],
            "keywords": dataset["keywords"] if "keywords" in dataset else [],
            "datePublished": dataset["datePublished"],
            "authors": authors,
            "license_id": license_id,
            "images": [],
            "link_rocrate": link_rocrate,
            "link_digital_object": link_digital_object,
            "provenance": prov_context,
            "date_modified": datetime.strptime(dataset["dateModified"], "%Y-%m-%dT%H:%M:%S.%fZ"),
            "date_created": datetime.strptime(dataset["dateCreated"], "%Y-%m-%dT%H:%M:%S.%fZ"),

        }

        # get list of items and their content type: tuple of absolute_url, content_type
        items = []
        for part_id in dataset["hasPart"]:
            item = next((elem for (key, elem) in objects.items() if key == part_id), None)
            if item is None:
                continue
            payload_contentUrl = item["contentUrl"]
            item_type = item["encodingFormat"]
            item_abs_url = self._connector.get_object_abs_url(part_id, payload_contentUrl)
            items.append((item_abs_url, item_type))

        # add images to page context:
        context["items"] = []
        for item in items:
            item_path = item[0].split("=")[-1]
            context["items"].append({
                "name": "/".join(item_path.split("/")[-2:]),
                "path": item_path,
                "url": item[0],
                "is_image": item[1].startswith("image"),
            })

        # render response and attach signposting links
        signposts = {
            "type": ["https://schema.org/ItemPage", "https://schema.org/Dataset"],
            "author": [author_url for (_, author_url) in authors],
            "license": license_id,
            "cite-as": [request.build_absolute_uri(reverse("dataset_detail", args=[id]))],
            "describedBy": [
                (link_rocrate, "application/ld+json"),
                (link_rocrate + "&download=true", "application/zip"),
                # (link_digital_object, "application/ld+json"),
            ],
            "item": items,

        }
        response = render(request, self.template_name, context)
        add_signposts(response, **signposts)

        return response

    def _build_ROCrate(self, request, id: str, objects: dict[str, dict[str, Any]], with_preview: bool = False, remote_urls: bool = False) -> ROCrate:
        crate = ROCrate(gen_preview=with_preview)
        dataset = objects[id]

        # TODO add sameAs identifier for digital objects that are not files?

        files_to_add = dataset.get("hasPart", [])
        if dataset.get("mainEntity") and dataset.get("mainEntity") not in files_to_add:
            files_to_add.append(dataset.get("mainEntity"))
        persons_to_add = dataset.get("author", [])
        actions_to_add = dataset.get("mentions", [])
        license_to_add = dataset.get("license")
        instruments_to_add = [action.get("instrument") for action in [objects[action_id] for action_id in actions_to_add]]

        id_to_crate_id = {}

        # add license
        if license_to_add is not None:
            license = crate.add(ContextEntity(crate, license_to_add, {"@type": "CreativeWork"}))
            id_to_crate_id[license_to_add] = license["@id"]

        # add persons
        for jsonld in map(lambda person_id: objects[person_id], persons_to_add):
            if "@context" in jsonld:
                del jsonld["@context"]
            if "affiliation" in jsonld:
                del jsonld["affiliation"]  # TODO add affiliation to crate
            person_id = jsonld.pop("@id")
            person_identifier = jsonld.pop("identifier", person_id)
            person = crate.add(Person(crate, identifier=person_identifier, properties=jsonld))
            id_to_crate_id[person_id] = person["@id"]

        # add all files
        for (part_id, file) in [(part_id, objects[part_id]) for part_id in files_to_add]:
            url = request.build_absolute_uri(self._connector.get_object_abs_url(file["@id"], file["contentUrl"]))
            if remote_urls:
                dest_path = None  # use payload URL as path
            else:
                dest_path = file["contentUrl"]
                file["sameAs"] = url
            del file["@id"]
            del file["@context"]
            del file["contentUrl"]
            if "isPartOf" in file:
                del file["isPartOf"]
            if "input" in file:
                for input_id in file["input"]:
                    input_jsonld = objects[input_id]
                    input = crate.add(ContextEntity(crate, input_id, properties=input_jsonld))
                    id_to_crate_id[input_id] = input["@id"]
                file["input"] = list(map(lambda id: {"@id": id_to_crate_id[id]}, file["input"]))
            if "output" in file:
                for output_id in file["output"]:
                    output_jsonld = objects[output_id]
                    output = crate.add(ContextEntity(crate, output_id, properties=output_jsonld))
                    id_to_crate_id[output_id] = output["@id"]
                file["output"] = list(map(lambda id: {"@id": id_to_crate_id[id]}, file["output"]))
            file["@type"] = list(map(lambda x: x.replace("MediaObject", "File"), file["@type"]))
            crate_file = crate.add_file(url, dest_path=dest_path, fetch_remote=False, properties=file | {
                "name": file["name"],
                "encodingFormat": file["encodingFormat"],
                "contentSize": file["contentSize"],
            })
            id_to_crate_id[part_id] = crate_file["@id"]

        # add instrument if not added yet (for softwareapplication)
        for instrument_id in filter(lambda id: "SoftwareApplication" in objects[id]["@type"], instruments_to_add):
            jsonld = objects[instrument_id]
            del jsonld["@context"]
            del jsonld["@id"]
            instrument = crate.add(ContextEntity(crate, instrument_id, properties=jsonld))
            id_to_crate_id[instrument_id] = instrument["@id"]

        # add actions
        for jsonld in map(lambda action_id: objects[action_id], actions_to_add):
            del jsonld["@context"]
            action_id = jsonld.pop("@id")
            if "agent" in jsonld:
                jsonld["agent"] = { "@id": id_to_crate_id[jsonld["agent"]] }

            if "instrument" in jsonld:
                jsonld["instrument"] = {"@id": id_to_crate_id[jsonld["instrument"]]}

            if "result" in jsonld:
                jsonld["result"] = list(map(lambda id: {"@id": id_to_crate_id[id]}, jsonld["result"]))

            if "object" in jsonld:
                for object_id in jsonld["object"]:
                    object_jsonld = objects[object_id]
                    object = crate.add(ContextEntity(crate, object_id, properties=object_jsonld))
                    id_to_crate_id[object_id] = object["@id"]
                jsonld["object"] = list(map(lambda id: {"@id": id_to_crate_id[id]}, jsonld["object"]))
            # TODO backlink to workflow
            action = crate.add(ContextEntity(crate, action_id, properties=jsonld))
            id_to_crate_id[action_id] = action["@id"]

        # update dataset entity
        for (key, value) in dataset.items():
            if key.startswith("@"):
                continue
            elif key in ["author", "hasPart", "mentions"]:
                value = list(map(lambda id: {"@id": id_to_crate_id[id]}, value))
            elif key in ["mainEntity", "license"]:
                value = {"@id": id_to_crate_id[value]}
            crate.root_dataset[key] = value

        # make this a valid workflow run RO-Crate
        crate.metadata.extra_contexts.append("https://w3id.org/ro/terms/workflow-run/context")
        crate.root_dataset["conformsTo"] = [
            {"@id": "https://w3id.org/ro/wfrun/process/0.1"},
            {"@id": "https://w3id.org/ro/wfrun/workflow/0.1"},
            {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"}
        ]
        crate.metadata["conformsTo"] = [
            {"@id": "https://w3id.org/ro/crate/1.1"},
            {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"}
        ]

        return crate

    def as_ROCrate(self, request, id: str, objects: dict[str, dict[str, Any]], download=False) -> HttpResponseBase:
        """ return a downloadable zip in RO-Crate format from the given dataset entity
        the zip file is build on the fly by streaming payload objects directly from the api

        params:
          id - the pid of the dataset
          objects - list of digital objects of the dataset
          download - return a downloadable zip in RO-Crate format
        """
        # Get crate metadata file (library does only support output to file)
        with tempfile.TemporaryDirectory() as temp_dir:
            crate = self._build_ROCrate(request, id, objects, with_preview = download, remote_urls=not download)
            crate.write(temp_dir)
            metadata = json.load(open(temp_dir + "/ro-crate-metadata.json", "r"))

            if download:
                # create a zip stream of ro crate files
                zs = zipstream.ZipFile(mode="w", compression=zipstream.ZIP_DEFLATED)
                zs.writestr("ro-crate-metadata.json", str.encode(json.dumps(metadata, indent=2)))
                html = open(temp_dir + "/ro-crate-preview.html", "r").read()
                zs.writestr("ro-crate-preview.html", str.encode(html))

                try:
                    for data_entity in crate.data_entities:
                        url = data_entity["sameAs"]
                        name = data_entity["@id"]
                        # url = request.build_absolute_uri(self._connector.get_object_abs_url(object["@id"], object["contentUrl"]))
                        # name = object["contentUrl"]
                        object_response = requests.get(url, verify=False, stream=True)
                        if object_response.status_code == 200:
                            zs.write_iter(name, object_response.iter_content(chunk_size=1024))
                        else:
                            raise Exception(f"Failed to add object file {url} to ro-crate zip stream: {object_response.text}")
                except Exception as e:
                    zs.close()
                    raise e

                archive_name = f'{id.replace("/", "_")}.zip'
                response = StreamingHttpResponse(zs, content_type="application/zip")
                response["Content-Disposition"] = f"attachment; filename={archive_name}"
                return response
            else:
                # return only metadata as json file
                return JsonResponse(metadata)

    def get(self, request, **kwargs):
        id = kwargs.get("id")

        # get digital object from cordra
        try:
            objects = self._connector.resolve_objects(id)
        except HTTPError as e:
            # Cordra responds with 401 if not a public object is not found.
            if e.response.status_code == 401:
                raise Http404
            raise


        if not id in objects or not "Dataset" in objects[id]["@type"]:
            raise Http404

        # return response:
        # - if requested in ROCrate format or as a zip , return the zipped RO-Crate
        # - if requested in json, redirect to the original digital object
        # - return the rendered http page otherwise
        response_format = None
        if "format" in request.GET:
            response_format = request.GET.get("format").lower()
        download = False
        if "download" in request.GET:
            download = request.GET.get("download").lower() == "true"
        accept = request.META.get("HTTP_ACCEPT", None).lower()

        if response_format == "rocrate":
            if download or accept == "application/zip":
                # return HttpResponse("not implemented yet", status=501)
                return self.as_ROCrate(request, id, objects, download=True)
            else:
                return self.as_ROCrate(request, id, objects, download=False)
        elif response_format == "json" or accept in ["application/json", "application/ld+json"]:
            return redirect(self._connector.get_object_abs_url(id))
        else:
            return self.render(request, id, objects)
