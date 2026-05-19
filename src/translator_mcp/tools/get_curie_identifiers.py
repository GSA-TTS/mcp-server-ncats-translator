import json
from typing import Annotated, Optional

from pydantic import Field

from translator_mcp.utils import handle_api_error, make_name_resolution_request


def register_get_curie_identifiers(mcp) -> None:
    @mcp.tool(
        name="translator_get_curie_identifiers",
        annotations={
            "title": "Get CURIE Identifiers by Name",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def translator_get_curie_identifiers(
        string: Annotated[str, Field(description="Name or synonym fragment to search for (e.g., 'diabetes', 'BRCA1', 'aspirin')", min_length=1, max_length=500)],
        limit: Annotated[Optional[int], Field(description="Maximum number of results to return (1–1000)", ge=1, le=1000)] = 10,
        offset: Annotated[Optional[int], Field(description="Number of results to skip for pagination", ge=0)] = 0,
        autocomplete: Annotated[Optional[bool], Field(description="Whether to match partial/prefix strings (default: true)")] = True,
        biolink_type: Annotated[Optional[list[str]], Field(description="Filter results to specific Biolink entity types (e.g., ['biolink:Disease', 'biolink:Gene'])")] = None,
        only_prefixes: Annotated[Optional[str], Field(description="Pipe-separated list of CURIE prefixes to include (e.g., 'MONDO|EFO|HP')")] = None,
        exclude_prefixes: Annotated[Optional[str], Field(description="Pipe-separated list of CURIE prefixes to exclude (e.g., 'UMLS|MESH')")] = None,
        only_taxa: Annotated[Optional[str], Field(description="Pipe-separated list of taxon IDs to filter results (e.g., 'NCBITaxon:9606' for human)")] = None,
    ) -> str:
        """Look up CURIE identifiers matching a name or synonym in the NCATS Translator Name Resolution service.

        Returns ranked matches with their CURIEs (Compact URIs), labels, synonyms, Biolink types, and relevance scores.
        CURIEs are the standard identifiers used across NCATS Translator APIs (e.g., MONDO:0005148, NCBIGene:672).

        Use when: "What is the CURIE for diabetes?" -> string="diabetes"
        Use when: "Find identifiers for BRCA1" -> string="BRCA1", biolink_type=["biolink:Gene"]
        Use when: "Look up MONDO IDs for Alzheimer's" -> string="Alzheimer", only_prefixes="MONDO"
        Don't use when: You already have a CURIE and need its synonyms (use translator_get_synonyms instead).

        Returns JSON with structure:
        [{"curie": str, "label": str, "synonyms": [str], "types": [str], "taxa": [str], "score": float, "clique_identifier_count": int}]

        Error responses:
        - "Error: Rate limit exceeded" — too many requests
        - "Error: Request timed out" — service unavailable
        - "No results found for '<string>'" — no matching identifiers
        """
        try:
            params: dict = {
                "string": string,
                "limit": limit,
                "offset": offset,
                "autocomplete": autocomplete,
            }
            if biolink_type:
                params["biolink_type"] = biolink_type
            if only_prefixes:
                params["only_prefixes"] = only_prefixes
            if exclude_prefixes:
                params["exclude_prefixes"] = exclude_prefixes
            if only_taxa:
                params["only_taxa"] = only_taxa

            results = await make_name_resolution_request("/lookup", params=params)

            if not results:
                return f"No results found for '{string}'"

            cleaned = [
                {
                    "curie": r.get("curie"),
                    "label": r.get("label"),
                    "types": r.get("types", []),
                    "synonyms": r.get("synonyms", []),
                    "taxa": r.get("taxa", []),
                    "score": r.get("score"),
                    "clique_identifier_count": r.get("clique_identifier_count"),
                }
                for r in results
            ]

            return json.dumps(
                {
                    "query": string,
                    "count": len(cleaned),
                    "offset": offset,
                    "has_more": len(cleaned) == limit,
                    "results": cleaned,
                },
                indent=2,
            )

        except Exception as e:
            return handle_api_error(e)
