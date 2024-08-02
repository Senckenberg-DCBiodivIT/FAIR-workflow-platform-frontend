import json
import tempfile
from typing import Any

import requests
import zipstream
from django.http import JsonResponse, HttpResponseBase, StreamingHttpResponse, Http404
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import TemplateView
from rocrate.model import ContextEntity, Person
from rocrate.rocrate import ROCrate

from cwr_frontend.cordra.CordraConnector import CordraConnector
from cwr_frontend.utils import add_signposts


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"
    _connector = CordraConnector()

    def to_typed_link_set(self,
                          abs_url: str,
                          author_urls: list[str],
                          license_url: str,
                          items: list[tuple[str, str]],
                          additional_urls: list[tuple[str, str]]) -> list[tuple[str, str, str | None]]:
        """ build a list of typed links for sign posting. """
        typed_links = [
            ("https://schema.org/Dataset", "type", None),
            ("https://schema.org/AboutPage", "type", None),
            (abs_url, "cite-as", None),
            (license_url, "license", None),
        ]
        typed_links += [(url, "author", None) for url in author_urls]
        typed_links += [(url, "describedBy", content_type) for (url, content_type) in additional_urls]
        typed_links += [(url, "item", content_type) for (url, content_type) in items]

        return typed_links

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
                "start_time": prov_start_time,
                "end_time": prov_end_time
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
            "provenance": prov_context
        }

        # get list of images and their content type
        items = []
        for part_id in dataset["hasPart"]:
            item = next((elem for (key, elem) in objects.items() if key == part_id), None)
            if item is None:
                continue
            payload_contentUrl = item["contentUrl"]
            item_type = item["encodingFormat"]
            item_abs_url = self._connector.get_object_abs_url(part_id, payload_contentUrl)
            is_image = item_type.startswith("image")
            items.append((item_abs_url, item_type, is_image))

        # add images to page: tuple of file_name, relative_url (or none if not an image)
        context["images"] = [(image[0].split("=")[-1], image[0], image[2]) for image in items]

        # render response and attach signposting links
        response = render(request, self.template_name, context)
        typed_links = self.to_typed_link_set(
            abs_url=request.build_absolute_uri(reverse("dataset_detail", args=[id])),
            author_urls=[author_url for (_, author_url) in authors],
            license_url=license_id,
            items=[(item[0], item[1]) for item in items],
            additional_urls=[
                (link_rocrate, "application/json+ld"),
                (link_rocrate + "&download=true", "application/zip"),
                (link_digital_object, "application/json+ld"),
            ]
        )
        add_signposts(response, typed_links)

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
            if "partOf" in file:
                del file["partOf"]
            if "resultOf" in file:
                del file["resultOf"]
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
                        name = data_entity["name"]
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
        objects = self._connector.resolve_objects(id)

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
