from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..schemas import CrawlJobRequest
from .crawler.manager import crawler_manager


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    example: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "example": self.example,
        }


def _crawler_tool() -> ToolSpec:
    request_schema = CrawlJobRequest.model_json_schema()
    example = {
        "keywords": ["ai regulation", "open source"],
        "seeds": [
            "https://example.com/relevant-article",
            "https://another-source.com/blog"
        ],
        "max_depth": 2,
        "max_pages": 40,
        "relevance_threshold": 0.4,
        "allow_external": False,
        "rate_limit": 1.0,
        "user_context": "Collect fresh articles about AI policy from trusted open-source communities.",
        "metadata": {"tags": ["policy", "opensource"]},
    }
    return ToolSpec(
        name="crawler.create_job",
        description="Schedule a focused crawl to gather relevant web articles for publication.",
        parameters=request_schema,
        example=example,
    )


_TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "crawler.create_job": _crawler_tool(),
}


def list_tools(names: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    if names is None:
        return [spec.to_dict() for spec in _TOOL_REGISTRY.values()]
    requested = []
    for name in names:
        spec = _TOOL_REGISTRY.get(name)
        if spec:
            requested.append(spec.to_dict())
    return requested


def build_system_prompt(tool_names: Optional[Iterable[str]] = None) -> str:
    selected = list_tools(tool_names)
    if not selected:
        return (
            "You are Nova, an autonomous assistant for the AILinux network. "
            "You do not have external tools available right now, so rely on your internal knowledge."
        )

    lines = [
        "You are Nova, an autonomous assistant for the AILinux network.",
        "You can call the following tools to gather or publish fresh information:",
    ]
    for tool in selected:
        lines.append(f"- {tool['name']}: {tool['description']}")
    lines.extend(
        [
            "When a tool is needed, respond *only* with JSON matching this schema:",
            '{"tool": "<name>", "arguments": { ... }}',
            "Return natural language answers when no tool call is required.",
        ]
    )
    return "\n".join(lines)


async def invoke_tool(
    tool_name: str,
    payload: Dict[str, Any],
    *,
    default_requested_by: Optional[str] = None,
) -> Dict[str, Any]:
    if tool_name not in _TOOL_REGISTRY:
        raise ValueError(f"Unknown tool '{tool_name}'")

    if tool_name == "crawler.create_job":
        request = CrawlJobRequest(**payload)
        data = request.model_dump()
        requested_by = data.get("requested_by") or default_requested_by
        job = await crawler_manager.create_job(
            keywords=data["keywords"],
            seeds=[str(url) for url in request.seeds],
            max_depth=data["max_depth"],
            max_pages=data["max_pages"],
            rate_limit=data["rate_limit"],
            relevance_threshold=data["relevance_threshold"],
            allow_external=data["allow_external"],
            user_context=data.get("user_context"),
            requested_by=requested_by,
            metadata=data.get("metadata") or {},
        )
        return job.to_dict()

    raise ValueError(f"Tool '{tool_name}' is registered but has no handler")
