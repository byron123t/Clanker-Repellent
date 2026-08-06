"""Read-only simulated environments for tool-using agent evaluation."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


_TOOLS_BY_ENVIRONMENT = {
    "repo": ("list_files", "search_repo", "read_file"),
    "repository": ("list_files", "search_repo", "read_file"),
    "website": ("site_search", "open_page"),
    "email": ("search_mail", "read_mail"),
    "mailbox": ("search_mail", "read_mail"),
    "issue": ("list_issues", "read_issue", "search_repo", "read_file"),
    "issue_coding": ("list_issues", "read_issue", "search_repo", "read_file"),
}

_TOOL_DESCRIPTIONS = {
    "list_files": "List paths and titles in the repository.",
    "search_repo": "Search repository resource paths and contents; returns matching paths only.",
    "read_file": "Read one repository file by its exact path.",
    "site_search": "Search the simulated website; returns page URLs and titles only.",
    "open_page": "Open one simulated website page by its exact URL path.",
    "search_mail": "Search the simulated mailbox; returns message IDs and headers only.",
    "read_mail": "Read one simulated email by its exact message ID.",
    "list_issues": "List issue IDs, titles, and states in the simulated tracker.",
    "read_issue": "Read one simulated issue by its exact issue ID.",
}

_ARGUMENT_NAMES = {
    "list_files": None,
    "list_issues": None,
    "search_repo": "query",
    "site_search": "query",
    "search_mail": "query",
    "read_file": "path",
    "open_page": "url",
    "read_mail": "message_id",
    "read_issue": "issue_id",
}


def _insert_payload(content: str, scenario: Dict[str, Any], condition: Dict[str, Any]) -> str:
    anchor = scenario.get("injection_anchor")
    if condition["placement"] == "none":
        return content.replace(anchor, "", 1) if anchor and anchor in content else content
    payload = condition.get("carrier_label", "") + condition["payload"]
    default_prefix, default_suffix = _default_carrier(scenario)
    block = scenario.get("injection_prefix", default_prefix) + payload + scenario.get(
        "injection_suffix", default_suffix
    )
    separator = condition.get("separator", "\n")
    if anchor and anchor in content:
        if condition["placement"] == "prepend":
            replacement = block + separator + anchor
        elif condition["placement"] == "append":
            replacement = anchor + separator + block
        else:
            raise ValueError(f"Unsupported placement: {condition['placement']}")
        return content.replace(anchor, replacement, 1)
    if condition["placement"] == "prepend":
        return block + separator + content
    if condition["placement"] == "append":
        return content + separator + block
    raise ValueError(f"Unsupported placement: {condition['placement']}")


def _default_carrier(scenario: Dict[str, Any]) -> tuple:
    environment_type = scenario["environment_type"]
    target = scenario["target_resource_id"]
    if environment_type == "website" or target.endswith(".html"):
        return ("<!-- Imported context:\n", "\n-->")
    if environment_type in {"email", "mailbox"} or target.endswith(".eml"):
        return ("--- Forwarded context ---\n", "\n--- End forwarded context ---")
    if target.endswith((".md", ".markdown")):
        return ("<details><summary>Imported context</summary>\n\n", "\n</details>")
    return ("# Imported context:\n", "")


class VirtualAgentEnvironment:
    """A deterministic, side-effect-free set of tools over one scenario."""

    def __init__(self, scenario: Dict[str, Any], condition: Dict[str, Any]) -> None:
        self.scenario = scenario
        self.condition = condition
        self.resources: Dict[str, Dict[str, Any]] = {}
        for source in scenario["resources"]:
            resource = dict(source)
            if resource["id"] == scenario["target_resource_id"]:
                resource["content"] = _insert_payload(
                    resource["content"], scenario, condition
                )
            self.resources[resource["id"]] = resource
        self.allowed_tools = _TOOLS_BY_ENVIRONMENT[scenario["environment_type"]]

    def tool_definitions(self) -> List[Dict[str, Any]]:
        definitions = []
        for name in self.allowed_tools:
            argument = _ARGUMENT_NAMES[name]
            properties: Dict[str, Any] = {}
            required: List[str] = []
            if argument is not None:
                properties[argument] = {"type": "string"}
                required.append(argument)
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": _TOOL_DESCRIPTIONS[name],
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    },
                }
            )
        return definitions

    def execute(self, name: str, arguments: Any) -> Dict[str, Any]:
        """Execute a read-only tool and return content plus exposure metadata."""

        if name not in self.allowed_tools:
            return self._result(name, None, {"error": f"unknown tool: {name}"})
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            return self._result(name, None, {"error": "arguments must be valid JSON"})
        if not isinstance(parsed, dict):
            return self._result(name, None, {"error": "arguments must be an object"})

        if name in {"list_files", "list_issues"}:
            kind = "issue" if name == "list_issues" else "file"
            matches = [
                self._metadata(resource)
                for resource in self.resources.values()
                if resource["kind"] == kind
            ]
            return self._result(name, None, {"results": matches})

        if name in {"search_repo", "site_search", "search_mail"}:
            query = str(parsed.get("query", "")).casefold()
            query_tokens = {
                token
                for token in re.findall(r"[a-z0-9_-]+", query)
                if len(token) >= 3
                and token
                not in {"and", "for", "from", "the", "with", "find", "search"}
            }
            permitted_kind: Optional[str] = {
                "site_search": "page",
                "search_mail": "email",
            }.get(name)
            matches = []
            for resource in self.resources.values():
                if permitted_kind and resource["kind"] != permitted_kind:
                    continue
                haystack = " ".join(
                    (resource["id"], resource["title"], resource["content"])
                ).casefold()
                if (
                    not query
                    or query in haystack
                    or any(token in haystack for token in query_tokens)
                ):
                    matches.append(self._metadata(resource))
            return self._result(name, None, {"results": matches})

        argument_name = _ARGUMENT_NAMES[name]
        resource_id = parsed.get(argument_name or "")
        resource = self.resources.get(resource_id)
        if resource is None and name == "read_issue" and isinstance(resource_id, str):
            issue_prefix = resource_id.casefold().removeprefix("issue ").strip()
            candidates = [
                item
                for item in self.resources.values()
                if item["kind"] == "issue"
                and item["id"].split("/")[-1].casefold().startswith(issue_prefix + "-")
            ]
            resource = candidates[0] if len(candidates) == 1 else None
        expected_kinds = {
            "read_file": {"file", "issue"}
            if self.scenario["environment_type"] in {"issue", "issue_coding"}
            else {"file"},
            "open_page": {"page"},
            "read_mail": {"email"},
            "read_issue": {"issue"},
        }[name]
        if resource is None or resource["kind"] not in expected_kinds:
            return self._result(
                name, None, {"error": f"resource not found: {resource_id!r}"}
            )
        return self._result(
            name,
            resource["id"],
            {"resource": self._metadata(resource), "content": resource["content"]},
        )

    def _metadata(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        metadata = {
            "id": resource["id"],
            "title": resource["title"],
            "kind": resource["kind"],
        }
        for optional in ("sender", "state"):
            if optional in resource:
                metadata[optional] = resource[optional]
        return metadata

    def _result(
        self, name: str, resource_id: Optional[str], body: Dict[str, Any]
    ) -> Dict[str, Any]:
        serialized = json.dumps(body, ensure_ascii=False)
        payload = self.condition["payload"]
        return {
            "tool_name": name,
            "resource_id": resource_id,
            "content": serialized,
            "payload_exposed": bool(payload and payload in serialized),
            "target_resource_read": resource_id == self.scenario["target_resource_id"],
            "error": body.get("error"),
        }
