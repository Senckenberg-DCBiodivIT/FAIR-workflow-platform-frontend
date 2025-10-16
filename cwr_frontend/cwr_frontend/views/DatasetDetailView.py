from datetime import datetime

from pyld import jsonld
from django.http import JsonResponse, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import TemplateView
from django_signposting.utils import add_signposts
from requests import HTTPError
from signposting import LinkRel, Signpost
import requests

from cwr_frontend.jsonld_utils import pyld_caching_document_loader, cached_frame
from cwr_frontend.cordra.CordraConnector import CordraConnector
from cwr_frontend.rocrate_io import as_ROCrate



class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"
    _connector = CordraConnector()

    def render(self, request, id: str, nested=False, workflow_only=False):
        """ Return a html representation with signposts from the given digital object """

        objects = self._connector.resolve_objects(id, nested=nested, workflow_only=workflow_only)
        dataset = objects[id]

        # tuples of author names and identifiers
        authors = [(elem["name"], elem.get("identifier")) for (elem_id, elem) in objects.items() if
                            "Person" in elem["@type"] and elem_id in dataset["author"]]

        license_id = dataset["license"] if "license" in dataset else None

        link_rocrate = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=ROCrate"
        link_digital_object = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=json"

        prov_action = next(iter(elem for (key, elem) in objects.items() if "CreateAction" in elem["@type"]), None)
        if prov_action is None:
            # if there is no provenance, check if there is a parent dataset to link to
            if "isPartOf" in dataset:
                prov_context = {
                    "parent_datasets": [(parent_id, request.build_absolute_uri(reverse("dataset_detail", args=[parent_id]))) for parent_id in dataset["isPartOf"]]
                }
            else:
                prov_context = None
        else:
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

        # render content
        context = {
            "id": id,
            "name": dataset.get("name"),
            "description": dataset.get("description"),
            "keywords": dataset.get("keywords", []),
            "datePublished": dataset.get("datePublished"),
            "authors": authors,
            "license_id": license_id,
            "images": [],
            "link_rocrate": link_rocrate,
            "link_digital_object": link_digital_object,
            "provenance": prov_context,
            "date_modified": datetime.strptime(dataset["dateModified"], "%Y-%m-%dT%H:%M:%S.%fZ"),
            "date_created": datetime.strptime(dataset["dateCreated"], "%Y-%m-%dT%H:%M:%S.%fZ"),
            "sd": self._jsonld(id, objects),
        }

        # get list of items and their content type: tuple of absolute_url, content_type
        items = []
        for part_id in dataset["hasPart"]:
            item = next((elem for (key, elem) in objects.items() if key == part_id), None)
            if item is None:
                continue
            if "Dataset" in item["@type"]:
                item_abs_url = request.build_absolute_uri(reverse("dataset_detail", args=[part_id]))
                items.append({
                    "name": item.get("name", "/".join(item_abs_url.split("/")[-2:])),
                    "url": item_abs_url,
                    "type": "dataset",
                    "image": None,
                })
            else:
                payload_contentUrl = item["contentUrl"]
                item_type = item.get("encodingFormat", "")
                item_abs_url = self._connector.get_object_abs_url(part_id, payload_contentUrl)
                items.append({
                    "name": "/".join(item_abs_url.split("payload=")[-1].split("/")[-1:]),
                    "url": item_abs_url,
                    "type": item_type,
                    "image": item_abs_url if item_type.startswith("image") else None,
                    "size_str": "{:.2f} MB".format(item["contentSize"] / 1024 / 1024)
                })

        # add images to page context:
        context["items"] = items

        # render response and attach signposting links
        signposts = [
            Signpost(LinkRel.type, "https://schema.org/ItemPage"),
            Signpost(LinkRel.type, "https://schema.org/Dataset"),
            Signpost(LinkRel.license, license_id),
            Signpost(LinkRel.cite_as, request.build_absolute_uri(reverse("dataset_detail", args=[id]))),
            Signpost(LinkRel.describedby, link_rocrate, "application/ld+json"),
            Signpost(LinkRel.describedby, link_rocrate + "&download=true", "application/zip"),
            # Signpost(LinkRel.described_by, link_digital_object, "application/ld+json"),
        ]
        for (_, author_url) in authors:
            signposts.append(Signpost(LinkRel.author, author_url))
        for item in items:
            item_url = requests.utils.requote_uri(item["url"])
            if item["type"] == "dataset":
                signposts.append(Signpost(LinkRel.item, item_url + "&format=ROCrate", "application/ld+json"))
            else:
                signposts.append(Signpost(LinkRel.item, item_url, item["type"]))
        response = render(request, self.template_name, context)
        add_signposts(response, *signposts)
        return response



    def get(self, request, **kwargs):
        id = kwargs.get("id")
        # get digital object from cordra
        try:
            object = self._connector.get_object_by_id(id)
        except HTTPError as e:
            # Cordra responds with 401 if not a public object is not found.
            if e.response.status_code == 401 or e.response.status_code == 404:
                raise Http404
            raise

        # return response:
        # - if requested in ROCrate format or as a zip , return the zipped RO-Crate
        # - if requested in json, return the digital object
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
                return as_ROCrate(request, id, download=True, connector=self._connector, workflow_only=False, nested=True)
            else:
                return as_ROCrate(request, id, download=False, connector=self._connector, workflow_only=False, nested=True)
        elif response_format == "workflowrocrate":
            return as_ROCrate(request, id, download=download or accept == "application/zip", connector=self._connector, workflow_only=True, nested=True)
        elif response_format == "json" or accept in ["application/json", "application/ld+json"]:
            return JsonResponse(object)
        else:
            return self.render(request, id, nested=False, workflow_only=False)

    def _jsonld(self, object_id, objects):
        jsonld.set_document_loader(pyld_caching_document_loader)
        framed = cached_frame({"@graph": list(objects.values())}, {"@context": "https://schema.org", "@graph": [{"name": objects[object_id]["name"]}]})
        framed["@type"] = ["Dataset", "ItemPage"]
        return framed
