from typing import Any

from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render, redirect
from django.urls import reverse
from cwr_frontend.utils import add_signpost
import requests
from django.http import StreamingHttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
import zipstream
import json


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"

    # get list of files to add to the archive
    def build_payload_abs_path(self, id: str, item_name: str) -> str:
        """ returns an absolute api path for the given payload """
        return reverse("api", args=[f"objects/{id}"]) + f"?payload={item_name}"

    def render(self, request, id: str, obj: dict[str, Any]):
        """ Return a html representation with signposts from the given digital object """
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))

        dataset_author_id = dataset["author"]["@id"]
        author = next((elem for elem in obj["@graph"] if elem["@id"] == dataset_author_id), None)
        author_name = author["name"]

        signposts = {"item": [
            (request.build_absolute_uri() + "&format=ROCrate", "application/zip"),
        ]}

        link_rocrate = request.build_absolute_uri() + "?format=ROCrate"
        link_digital_object= request.build_absolute_uri() + "?format=json"

        # render content
        context = {
            "id": id,
            "name": dataset["name"],
            "description": dataset["description"],
            "keywords": dataset["keywords"],
            "datePublished": dataset["datePublished"],
            "author": author_name,
            "author_id": dataset_author_id,
            "images": [],
            "link_rocrate": link_rocrate,
            "link_digital_object": link_digital_object,
        }

        for part in dataset["hasPart"]:
            part_id = part["@id"]
            item = next((elem for elem in obj["@graph"] if elem["@id"] == part_id), None)
            if item is None:
                continue
            item_id = part_id
            item_type = item["encodingFormat"]
            if (item_type.startswith("image")):
                item_abs_url = self.build_payload_abs_path(id, item_id)
                signposts["item"].append((item_abs_url, item_type))
                context["images"].append(item_abs_url)

        response = render(request, self.template_name, context)

        # attach signposting headers
        signposts |= {
            "cite-as": [(request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])), "related")],
            "author": [dataset_author_id],
            "license": [dataset["license"]["@id"]],
        }
        add_signpost(response, signposts)

        return response

    def to_ROCrate(self, request, id: str, obj: dict) -> StreamingHttpResponse:
        """ return a downloadable zip in RO-Crate format from the given dataset entity
        the zip file is build on the fly by streaming payload objects directly from the api

        params:
          id - the pid of the dataset
          obj - the json object of the dataset
        """

        # get list of files to add to the archive
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))
        files_to_add = {}  # {filename: file_abs_url}
        for file in dataset["hasPart"]:
            file_name = file["@id"]
            file_abs_url = request.build_absolute_uri(self.build_payload_abs_path(id, file_name))
            files_to_add[file_name] = file_abs_url

        # prepare a streamable zip response
        # this does not allocate memory on the server (hopefully)
        zs = zipstream.ZipFile(mode="w", compression=zipstream.ZIP_DEFLATED)

        # add ro-crate-metadata.json to the archive
        zs.writestr("ro-crate-metadata.json", str.encode(json.dumps(obj, indent=2)))

        # add payload files
        for (name, url) in files_to_add.items():
            response = requests.get(url, verify=False, stream=True)
            if response.status_code == 200:
                zs.write_iter(name, response.iter_content(chunk_size=1024))
            else:
                raise Exception("Failed to add file to ro-crate zip stream: " + response.text)

        archive_name = f'{id.replace("/", "_")}.zip'
        response = StreamingHttpResponse(zs, content_type="application/zip")
        response['Content-Disposition'] = f'attachment; filename={archive_name}'
        return response

    def get(self, request, **kwargs):
        id = kwargs.get("id")

        # get digital object from cordra
        url = settings.CORDRA["URL"] + "/objects/" + id
        response = requests.get(url, verify=False)
        if response.status_code == 400:
            return HttpResponseNotFound("Object with PID " + id + " not found")
        elif response.status_code != 200:
            return HttpResponseServerError(
                f"Could not receive object with PID {id} (Backend responded with {response.status_code})"
        )

        json_obj = response.json()

        # return response:
        # - if requested in ROCrate format or as a zip , return the zipped RO-Crate
        # - if requested in json, redirect to the original digital object
        # - return the rendered http page otherwise
        response_format = None
        if "format" in request.GET:
            response_format = request.GET.get("format").lower()
        accept = request.META.get("HTTP_ACCEPT", None).lower()

        if response_format == "rocrate" or accept == "application/zip":
            return self.to_ROCrate(request, id, json_obj)
        elif response_format == "json" or accept in ["application/json", "application/ld+json"]:
            return JsonResponse(json_obj)
        else:
            return self.render(request, id, json_obj)


