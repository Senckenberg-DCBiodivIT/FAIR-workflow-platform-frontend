import json
import os
import tempfile
from copy import deepcopy
from tempfile import NamedTemporaryFile
from typing import Any

from django.http import JsonResponse, FileResponse, HttpResponseBase
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import TemplateView
from rocrate.model import ContextEntity
from rocrate.rocrate import ROCrate

from cwr_frontend.cordra.CordraConnector import CordraConnector
from cwr_frontend.utils import add_signposts


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"
    _connector = CordraConnector()

    # get list of files to add to the archive
    def build_payload_abs_path(self, id: str, item_name: str) -> str:
        """ returns an absolute api path for the given payload """
        return reverse("api", args=[f"objects/{id}"]) + f"?payload={item_name}"

    def to_typed_link_set(self,
                          abs_url: str,
                          author_url: str,
                          license_url: str,
                          items: list[tuple[str, str]],
                          additional_urls: list[tuple[str, str]]) -> list[tuple[str, str, str | None]]:
        """ build a list of typed links for sign posting. """
        typed_links = [
            ("https://schema.org/Dataset", "type", None),
            ("https://schema.org/AboutPage", "type", None),
            (abs_url, "cite-as", None),
            (author_url, "author", None),
            (license_url, "license", None),
        ]
        typed_links += [(url, "describedBy", content_type) for (url, content_type) in additional_urls]
        typed_links += [(url, "item", content_type) for (url, content_type) in items]

        return typed_links

    def render(self, request, id: str, objects: dict[str, dict[str, Any]]):
        """ Return a html representation with signposts from the given digital object """
        dataset = objects[id]

        # TODO support multiple authors and no author
        author = next(iter([elem for (elem_id, elem) in objects.items() if
                            elem["@type"] == "Person" and elem_id in dataset["author"]]), None)
        dataset_author_id = author["identifier"]
        author_name = author["name"]

        license_id = dataset["license"] if "license" in dataset else None

        link_rocrate = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=ROCrate"
        link_digital_object = request.build_absolute_uri(reverse("dataset_detail", args=[id])) + "?format=json"

        prov_action = next(iter(elem for (key, elem) in objects.items() if elem["@type"] == "CreateAction"), None)
        prov_action_name = prov_action["@type"]
        prov_instrument_id = prov_action["instrument"]["@id"] if "instrument" in prov_action else None
        prov_agent_internal_id = prov_action["agent"]
        prov_agent = next(iter(elem for (key, elem) in objects.items() if elem["@id"] == prov_agent_internal_id), None)
        prov_agent_id = prov_agent["identifier"]
        prov_agent_name = prov_agent["name"]

        # render content
        context = {
            "id": id,
            "name": dataset["name"],
            "description": dataset["description"],
            "keywords": dataset["keywords"] if "keywords" in dataset else [],
            "datePublished": dataset["datePublished"],
            "author": author_name,
            "author_id": dataset_author_id,
            "license_id": license_id,
            "images": [],
            "link_rocrate": link_rocrate,
            "link_digital_object": link_digital_object,
            "prov_action": prov_action_name,
            "prov_agent_id": prov_agent_id,
            "prov_agent_name": prov_agent_name,
            "prov_instrument_id": prov_instrument_id,
        }

        # get list of images and their content type
        items = []
        for part_id in dataset["hasPart"]:
            item = next((elem for (key, elem) in objects.items() if key == part_id), None)
            if item is None:
                continue
            item_id = item["name"]
            item_type = item["encodingFormat"]
            item_abs_url = request.build_absolute_uri(
                reverse("api", args=[f"objects/{part_id}"]) + f"?payload={item_id}")
            is_image = item_type.startswith("image")
            items.append((item_abs_url, item_type, is_image))

        # add images to page: tuple of file_name, relative_url (or none if not an image)
        context["images"] = [(image[0].split("=")[-1], image[0], image[2]) for image in items]

        # render response and attach signposting links
        response = render(request, self.template_name, context)
        typed_links = self.to_typed_link_set(
            abs_url=request.build_absolute_uri(reverse("dataset_detail", args=[id])),
            author_url=dataset_author_id,
            license_url=license_id,
            items=[(item[0], item[1]) for item in items],
            additional_urls=[
                (link_rocrate, "application/zip"),
                (link_digital_object, "application/json+ld"),
            ]
        )
        add_signposts(response, typed_links)

        return response

    def _build_ROCrate(self, request, id: str, objects: dict[str, dict[str, Any]], fetch_remote: bool = False) -> ROCrate:
        objects = deepcopy(objects)  # editing elements in place messes with django cache

        dataset = objects[id]

        added_persons = []
        crate = ROCrate()

        for property in ["name", "description", "dateCreated", "studySubject", "datePublished", "dateModified",
                         "keywords"]:
            if (property in dataset) and (dataset[property] is not None):
                crate.root_dataset[property] = dataset[property]

        for author in map(lambda author_id: objects[author_id], dataset["author"]):
            author = deepcopy(author)
            author_id = author.pop("@id")
            crate_author = crate.add(ContextEntity(crate, author_id, properties=author))
            crate.root_dataset.append_to("author", crate_author)
            added_persons.append(author_id)

        crate.license = crate.add(ContextEntity(crate, dataset["license"], properties={"@type": "CreativeWork"}))
        crate.root_dataset["sameAs"] = request.build_absolute_uri(reverse("api", args=[f"objects/{id}"]))

        # add all files
        for file in [objects[part_id] for part_id in objects if objects[part_id]["@type"] == "MediaObject"]:
            url = request.build_absolute_uri(self.build_payload_abs_path(file["@id"], file["name"]))
            if fetch_remote:
                dest_path = file["name"]
            else:
                dest_path = None  # use payload URL as path
            crate.add_file(url, dest_path=dest_path, fetch_remote=fetch_remote, properties={
                "name": file["name"],
                "encodingFormat": file["encodingFormat"],
                "contentSize": file["contentSize"]
            })

        for action in map(lambda mention_id: objects[mention_id], dataset["mentions"]):
            action_id = action.pop("@id")
            agent_id = action.get("agent", None)
            action = crate.add(ContextEntity(crate, action_id, properties=action))
            if agent_id:
                agent = objects[agent_id]
                agent = deepcopy(agent)
                agent_id = agent.pop("@id")
                added_agent = crate.add(ContextEntity(crate, agent_id, properties=agent))
                added_persons.append(agent_id)
                action["agent"] = added_agent
            results_id = action.get("result", [])
            del (action["result"])
            for file in map(lambda id: objects[id], results_id):
                url = request.build_absolute_uri(self.build_payload_abs_path(file["@id"], file["name"]))
                if fetch_remote:
                    dest_path = file["name"]
                else:
                    dest_path = None  # use payload URL as path
                crate_result_file = crate.add_file(url, dest_path=dest_path, fetch_remote=fetch_remote, properties={
                    "name": file["name"],
                    "encodingFormat": file["encodingFormat"],
                    "contentSize": file["contentSize"]
                })
                action.append_to("result", crate_result_file)

            if "instrument" in action:
                instrument = deepcopy(objects[action_id]["instrument"])
                instrument_id = instrument.pop("@id")
                action["instrument"] = crate.add(ContextEntity(crate, instrument_id, properties=instrument))
            crate.root_dataset.append_to("mentions", action)

        return crate

    def as_ROCrate(self, request, id: str, objects: dict[str, dict[str, Any]], download=False) -> HttpResponseBase:
        """ return a downloadable zip in RO-Crate format from the given dataset entity
        the zip file is build on the fly by streaming payload objects directly from the api

        params:
          id - the pid of the dataset
          objects - list of digital objects of the dataset
          download - return a downloadable zip in RO-Crate format
        """
        if download:
            crate = self._build_ROCrate(request, id, objects, fetch_remote=True)
            temp_file = NamedTemporaryFile(suffix=".zip", delete=False)
            try:
                crate.write_zip(temp_file.name)
                temp_file.flush()
                temp_file.seek(0)

                archive_name = f'{id.replace("/", "_")}.zip'
                response = FileResponse(temp_file, as_attachment=True, filename=archive_name)
                def clean():
                    os.remove(temp_file.name)
                response.close = clean
                return response
            except Exception as e:
                temp_file.close()
                os.remove(temp_file.name)
                raise e
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                crate = self._build_ROCrate(request, id, objects, fetch_remote=False)
                crate.write(temp_dir)
                metadata = json.load(open(temp_dir + "/ro-crate-metadata.json", "r"))
                return JsonResponse(metadata)

    def get(self, request, **kwargs):
        id = kwargs.get("id")

        # get digital object from cordra
        objects = self._connector.resolve_objects(id)

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
                return self.as_ROCrate(request, id, objects, download=True)
            else:
                return self.as_ROCrate(request, id, objects, download=False)
        elif response_format == "json" or accept in ["application/json", "application/ld+json"]:
            return redirect(request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])))
        else:
            return self.render(request, id, objects)
