import asyncio
import json
import time
from typing import Annotated, Any, Optional

import httpx
from pydantic import Field

from translator_mcp.resolver import resolve_name_to_curie
from translator_mcp.utils import (
    handle_api_error,
    make_ars_results_request,
    make_ars_status_request,
    make_ars_submit_request,
)

ARAX_BASE_URL = "https://arax.ncats.io/?source=ARS&id="
POLL_INTERVAL = 10  # seconds between ARS status checks


def _build_query_graph(nodes: list[dict], edges: list[dict]) -> dict:
    qnodes = {}
    for node in nodes:
        node_id = node["node_id"]
        spec: dict[str, Any] = {}
        if node.get("curies"):
            spec["ids"] = node["curies"]
        if node.get("categories"):
            spec["categories"] = node["categories"]
        qnodes[node_id] = spec

    qedges = {}
    for edge in edges:
        edge_id = edge["edge_id"]
        spec = {
            "subject": edge["subject"],
            "object": edge["object"],
        }
        if edge.get("predicates"):
            spec["predicates"] = edge["predicates"]
        qedges[edge_id] = spec

    return {"nodes": qnodes, "edges": qedges}


def _resolve_node_name(curie: str, kg_nodes: dict) -> str:
    node_data = kg_nodes.get(curie, {})
    return node_data.get("name") or curie


def _summarize_agent_results(
    results: list,
    kg_nodes: dict,
    query_node_ids: list[str],
    max_results: int,
) -> list[dict]:
    summarized = []
    for result in results[:max_results]:
        node_bindings: dict[str, dict] = {}
        for qnode_id in query_node_ids:
            bindings = result.get("node_bindings", {}).get(qnode_id, [])
            if bindings:
                curie = bindings[0].get("id", "")
                node_bindings[qnode_id] = {
                    "id": curie,
                    "name": _resolve_node_name(curie, kg_nodes),
                }
        entry: dict[str, Any] = {"node_bindings": node_bindings}
        score = result.get("analyses", [{}])[0].get("score") if result.get("analyses") else result.get("score")
        if score is not None:
            entry["score"] = score
        summarized.append(entry)
    return summarized


def register_query_knowledge_graph(mcp) -> None:
    @mcp.tool(
        name="translator_query_knowledge_graph",
        annotations={
            "title": "Query NCATS Translator Knowledge Graph",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def translator_query_knowledge_graph(
        nodes: Annotated[list[dict], Field(description=(
            "List of query nodes. Each node is a dict with:\n"
            "  - 'node_id' (str, required): local reference ID used to wire edges, e.g. 'n00'\n"
            "  - 'name' (str, optional): natural-language name to resolve automatically to a CURIE, e.g. 'aspirin'\n"
            "  - 'curies' (list[str], optional): known CURIE identifiers if already available, e.g. ['MONDO:0005015']\n"
            "  - 'categories' (list[str], optional): Biolink type constraints, e.g. ['biolink:Disease']\n"
            "Anchor nodes (known entities) provide either 'name' or 'curies'; unknown nodes (what you're querying for) provide only 'categories'.\n"
            "Providing 'name' triggers automatic CURIE lookup via name resolution + normalization.\n"
            "Example with names: [\n"
            "  {'node_id': 'n00', 'name': 'aspirin', 'categories': ['biolink:ChemicalEntity']},\n"
            "  {'node_id': 'n01', 'categories': ['biolink:Disease']}\n"
            "]\n"
            "Example with CURIEs: [\n"
            "  {'node_id': 'n00', 'curies': ['CHEBI:15365'], 'categories': ['biolink:ChemicalEntity']},\n"
            "  {'node_id': 'n01', 'categories': ['biolink:Disease']}\n"
            "]"
        ))],
        edges: Annotated[list[dict], Field(description=(
            "List of query edges. Each edge is a dict with:\n"
            "  - 'edge_id' (str, required): local reference ID, e.g. 'e00'\n"
            "  - 'subject' (str, required): node_id of the subject node\n"
            "  - 'object' (str, required): node_id of the object node\n"
            "  - 'predicates' (list[str], optional): Biolink predicates. Omit to match any relationship.\n"
            "Example: [\n"
            "  {'edge_id': 'e00', 'subject': 'n00', 'object': 'n01', 'predicates': ['biolink:entity_negatively_regulates_entity']},\n"
            "  {'edge_id': 'e01', 'subject': 'n01', 'object': 'n02', 'predicates': ['biolink:related_to']}\n"
            "]"
        ))],
        max_results_per_agent: Annotated[Optional[int], Field(
            description="Maximum results to return per agent (default: 10)",
            ge=1, le=100,
        )] = 10,
        timeout_seconds: Annotated[Optional[int], Field(
            description="How long to wait for ARS results before returning partial data (default: 180s, max: 300s)",
            ge=30, le=300,
        )] = 180,
    ) -> str:
        """Query the NCATS Translator Autonomous Relay System (ARS) with a biomedical knowledge graph query.

        Submits a TRAPI query graph to the ARS, which fans it out to all registered reasoning agents
        (ARAGORN, ARAX, ROBOKOP, BTE, etc.), polls every 10 seconds until results arrive, then returns
        a summary of the top results from each agent that responded.

        Use when: "What genes does aspirin negatively regulate that relate to dry mouth?"
        Use when: "Find diseases associated with TP53 mutations"
        Use when: "What pathways connect metformin to diabetes?"

        Each node needs a 'node_id' for edge wiring. Anchor nodes (known entities) provide either
        a 'name' (resolved automatically to a CURIE) or 'curies' directly. Unknown nodes (what
        you're querying for) get only 'categories'. Resolved names are reported in 'resolved_nodes'
        in the output so callers can verify the mapping.

        Returns JSON with ARAX URL for full interactive exploration, plus top results per agent with
        human-readable node names resolved from each agent's knowledge graph.

        Error responses:
        - "Error: ARS submission failed" — ARS unreachable or rejected query
        - {"query_status": "Timeout"} — no agent responded within timeout_seconds
        - {"query_status": "Partial"} — some agents responded before timeout
        """
        query_node_ids = [n["node_id"] for n in nodes]

        # 1. Resolve any nodes specified by name rather than CURIE
        resolved_names: dict[str, dict] = {}
        nodes = [dict(n) for n in nodes]  # shallow copy so we can mutate
        for node in nodes:
            if node.get("name") and not node.get("curies"):
                try:
                    curie, label = await resolve_name_to_curie(
                        node["name"], node.get("categories")
                    )
                    node["curies"] = [curie]
                    resolved_names[node["node_id"]] = {
                        "input_name": node["name"],
                        "resolved_curie": curie,
                        "resolved_label": label,
                    }
                except ValueError as e:
                    return f"Error resolving node '{node['node_id']}': {e}"

        # 2. Build TRAPI message
        query_graph = _build_query_graph(nodes, edges)
        message = {"message": {"query_graph": query_graph}}

        # 2. Submit to ARS
        try:
            submit_response = await make_ars_submit_request("/submit", json=message)
        except httpx.HTTPStatusError as e:
            return f"Error: ARS submission failed with status {e.response.status_code}: {e.response.text}"
        except Exception as e:
            return handle_api_error(e)

        message_id = submit_response.get("pk")
        if not message_id:
            return f"Error: ARS submission did not return a message ID. Response: {submit_response}"

        arax_url = f"{ARAX_BASE_URL}{message_id}"

        # 3. Poll until Done or timeout
        start = time.monotonic()
        status_data: dict = {}
        query_status = "Running"

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_seconds:
                query_status = "Timeout"
                break
            try:
                status_data = await make_ars_status_request(f"/messages/{message_id}", params={"trace": "y"})
                query_status = status_data.get("status", "Unknown")
                if query_status == "Done":
                    break
            except Exception:
                pass  # transient poll error — keep trying until timeout

            await asyncio.sleep(POLL_INTERVAL)

        elapsed_seconds = round(time.monotonic() - start)

        # 4. Collect results from Done children
        results_by_agent: dict[str, dict] = {}
        timed_out_agents: list[str] = []

        for child in status_data.get("children", []):
            agent_name = child.get("actor", {}).get("agent", "unknown")
            child_status = child.get("status", "")

            if child_status != "Done":
                if child_status in ("Running", "Queued", "Accepted"):
                    timed_out_agents.append(agent_name)
                continue

            child_message_id = child.get("message")
            if not child_message_id:
                continue

            try:
                child_data = await make_ars_results_request(f"/messages/{child_message_id}")
                agent_message = child_data["fields"]["data"]["message"]
                agent_results = agent_message.get("results") or []
                kg_nodes = (agent_message.get("knowledge_graph") or {}).get("nodes") or {}

                if not agent_results:
                    continue

                results_by_agent[agent_name] = {
                    "total_results": len(agent_results),
                    "showing": min(len(agent_results), max_results_per_agent),
                    "results": _summarize_agent_results(
                        agent_results, kg_nodes, query_node_ids, max_results_per_agent
                    ),
                }
            except Exception:
                continue  # skip agents whose result fetch fails

        # Resolve final status label
        if query_status == "Timeout" and results_by_agent:
            query_status = "Partial"

        output: dict[str, Any] = {
            "message_id": message_id,
            "arax_url": arax_url,
            "query_status": query_status,
            "elapsed_seconds": elapsed_seconds,
            "agents_responded": len(results_by_agent),
            "results_by_agent": results_by_agent,
        }
        if resolved_names:
            output["resolved_nodes"] = resolved_names
        if timed_out_agents:
            output["agents_still_running"] = timed_out_agents

        return json.dumps(output, indent=2)
