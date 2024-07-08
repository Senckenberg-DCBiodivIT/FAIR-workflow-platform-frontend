from typing import Any
from urllib.parse import urlencode
import requests
from django.conf import settings

class CordraConnector:

    def __init__(self, base_url=settings.CORDRA["URL"], prefix=settings.CORDRA["PREFIX"], user=None, password=None):
        self._base_url = base_url
        self.user = user
        self.password = password
        if prefix.endswith("/"):
            self.prefix = prefix
        else:
            self.prefix = prefix + "/"

    def list_datasets(self, page_size=100, page_num=0) -> list[dict[str, str]]:
        """ retrieve list of objects from cordra """
        params = {
            "pageNum": page_num,
            "pageSize": page_size,
            "query": "type:Dataset"
        }
        url = f"{self._base_url}/search?{urlencode(params)}"
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        return response.json()

    def get_object_by_id(self, id: str) -> dict[str, Any]:
        """ retrieve object from cordra. Raises if the object was not found. """
        url = settings.CORDRA["URL"] + "/objects/" + id
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(
                f"Could not receive object with PID {id} (Backend responded with {response.status_code})"
            )

        return response.json()

    def resolve_objects(self, object_id: str, resolved_objects=None, max_recursion = 2) -> dict[str, [dict[str, Any]]]:
        """ Recursively resolves cordra objects until the max recursion depth is reached.
        Returns a map of all resolved objects in the form {object_id: object}
        """
        if resolved_objects is None:
            resolved_objects = {}

        if not object_id in resolved_objects:
            root_obj = self.get_object_by_id(object_id)
            resolved_objects[object_id] = root_obj
        else:
            root_obj = resolved_objects[object_id]

        # resolve referenced objects until recursion depth is reached
        if max_recursion > 0:
            def resolve_links(json, resolved_objects):
                for key, value in json.items():
                    if key == "@id": continue
                    if isinstance(value, str) and value.startswith(self.prefix) and value not in resolved_objects:
                        resolved_objects |= self.resolve_objects(value, resolved_objects, max_recursion=max_recursion-1)
                    elif isinstance(value, list):
                        for i in range(len(value)):
                            if isinstance(value[i], str) and value[i].startswith(self.prefix) and value[i] not in resolved_objects:
                                resolved_objects |= self.resolve_objects(value[i], resolved_objects, max_recursion=max_recursion-1)
                    elif isinstance(value, dict):
                        resolve_links(value, resolved_objects)
            resolve_links(root_obj, resolved_objects)

        return resolved_objects

