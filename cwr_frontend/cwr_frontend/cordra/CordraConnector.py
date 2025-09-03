from itertools import batched
from typing import Any
from urllib.parse import urlencode, urljoin
import requests
from django.conf import settings
from django.core.cache import cache


class CordraConnector:

    def __init__(self, base_url=settings.CORDRA["URL"], prefix=settings.CORDRA["PREFIX"], 
                 user=settings.CORDRA["USER"], password=settings.CORDRA["PASSWORD"]):
        self._base_url = base_url
        if not self._base_url.endswith("/"):
            self._base_url += "/"
        self.user = user
        self.password = password
        self.prefix = prefix
        if not self.prefix.endswith("/"):
            self.prefix = prefix + "/"

    def get_object_abs_url(self, id: str, payload_name: str | None = None) -> str:
        """ Builds the absolute url to a cordra object. If payload name is given, returns the url to the payload."""
        url = urljoin(self._base_url, f"objects/{id}")
        if payload_name is not None:
            url += f"?payload={payload_name}"
        return url

    def list_datasets(self, page_num=0, page_size=25, include_nested: bool = False) -> list[dict[str, str]]:
        """ retrieve list of objects from cordra """
        query = "type:Dataset"
        if not include_nested:
            query += " AND NOT /isPartOf/_:[* TO *]"  # exclude datasets with the isPartOf property
        params = {
            "pageNum": page_num,
            "pageSize": page_size,
            "query": query,
            "sortFields": 'metadata/modifiedOn DESC '
        }
        url = f'{urljoin(self._base_url, "search")}?{urlencode(params)}'
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        return response.json()

    def get_object_by_id(self, id: str) -> dict[str, Any]:
        """ retrieve object from cordra. Raises if the object was not found. """
        url = self.get_object_abs_url(id)
        response = requests.get(url, verify=False)
        response.raise_for_status()

        return response.json()

    def search_for_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        url = urljoin(self._base_url, "search")
        url = f"{url}?{urlencode({'query': ' OR '.join(['id:' + id for id in ids])})}"
        response = requests.get(url, verify=False)
        response.raise_for_status()

        return response.json()["results"]


    def _resolve(self, object_ids: list[str], resolved_objects=None, max_recursion=3) -> dict[str, dict[str, Any]]:
        if resolved_objects is None:
            resolved_objects = {}

        if max_recursion == 0:
            raise Exception("Maximum recursion depth reached while resolving cordra objects. This is probably a bug.")

        newly_resolved_objects = []
        for id_batch in batched(object_ids, 200):  # cordra throws 502 if request becomes too large
            newly_resolved_objects += self.search_for_ids(id_batch)
        for obj in newly_resolved_objects:
            resolved_objects[obj["id"]] = obj["content"]

        def find_all_ids_in_obj(obj: dict[str, Any], ids_to_resolve: set[str] | None = None):
            if ids_to_resolve is None:
                ids_to_resolve = set()

            for (key, value) in obj.items():
                if key == "@id": continue

                if isinstance(value, dict):
                    find_all_ids_in_obj(value, ids_to_resolve)
                elif isinstance(value, list):
                    for possible_id in value:
                        if isinstance(possible_id, str) and possible_id.startswith(self.prefix):
                            ids_to_resolve.add(possible_id)
                elif isinstance(value, str) and value.startswith(self.prefix):
                    ids_to_resolve.add(value)
            return ids_to_resolve

        discovered_ids = []
        for obj in newly_resolved_objects:
            discovered_ids += find_all_ids_in_obj(obj["content"])
        discovered_ids = list(set([id for id in discovered_ids if id not in resolved_objects]))

        if len(discovered_ids) == 0:
            return resolved_objects
        else:
            return self._resolve(discovered_ids, resolved_objects, max_recursion - 1)

    def _resolve_object_graph(self, id: str, nested, workflow_only) -> list[dict[str, Any]]:
        url = urljoin(self._base_url, "cordra/call")
        params = {
            "objectId": id,
        }
        if workflow_only:
            if nested:
                params["method"] = "asNestedWorkflowGraph"
            else:
                params["method"] = "asWorkflowGraph"
        else:
            if nested:
                params["method"] = "asNestedGraph"
            else:
                params["method"] = "asGraph"
        url = f"{url}?{urlencode(params)}"
        response = requests.get(url, verify=False, auth=(self.user, self.password))
        response.raise_for_status()

        return response.json()["@graph"]

    def resolve_objects(self, object_id: str, nested: bool = False, workflow_only: bool = False) -> dict[str, [dict[str, Any]]]:
        """ Recursively resolves cordra objects until the max recursion depth is reached.
        Returns a map of all resolved objects in the form {object_id: object}
        """
        cache_key = f"dataset-objects-{object_id}-nested={nested}-workflow_only={workflow_only}"
        objects = cache.get(cache_key)
        if objects is None:
            objects = dict(map(lambda obj: (obj["@id"], obj), self._resolve_object_graph(object_id, nested, workflow_only)))
            cache.set(cache_key, objects, 15*60)
        return objects
