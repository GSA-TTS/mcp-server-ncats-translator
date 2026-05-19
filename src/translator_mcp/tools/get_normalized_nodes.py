import json
from typing import Annotated, Optional

from pydantic import Field

from translator_mcp.utils import handle_api_error, make_node_normalization_request


def register_get_normalized_nodes(mcp) -> None:
    @mcp.tool(
        name="translator_get_normalized_nodes",
        annotations={
            "title": "Get Normalized Nodes",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def translator_get_normalized_nodes(
        curies: Annotated[list[str], Field(description="One or more CURIEs to normalize (e.g., ['MONDO:0005015', 'NCBIGene:672'])", min_length=1)],
        conflate: Annotated[Optional[bool], Field(description="Apply gene/protein conflation — treats genes and their protein products as equivalent (default: true)")] = True,
        drug_chemical_conflate: Annotated[Optional[bool], Field(description="Apply drug/chemical conflation — merges drug and chemical entities (default: true)")] = True,
        include_descriptions: Annotated[Optional[bool], Field(description="Include text descriptions for each CURIE when available (default: false)")] = False,
        include_taxa: Annotated[Optional[bool], Field(description="Include taxonomic information in results (default: true)")] = True,
        limit_equivalent_ids: Annotated[Optional[int], Field(description="Cap the number of equivalent identifiers returned per node to avoid overwhelming output (0 = no limit)", ge=0)] = 20,
    ) -> str:
        """Normalize CURIEs using the NCATS Translator Node Normalization service.

        For each input CURIE, returns:
        - The canonical/preferred identifier and label
        - Equivalent identifiers across ontologies (MONDO, DOID, MESH, UMLS, NCIT, etc.)
        - Biolink entity types (e.g., biolink:Disease, biolink:Gene)
        - Information content score (higher = more specific)
        - Taxonomic scope (for genes/proteins)

        Use when: "What is the canonical ID for DOID:9351?" -> curies=["DOID:9351"]
        Use when: "Find all equivalent IDs for BRCA1" -> curies=["NCBIGene:672"]
        Use when: "Normalize a batch of CURIEs" -> curies=["MONDO:0005015", "HP:0000819"]
        Don't use when: You have a name and need a CURIE (use translator_get_curie_identifiers instead).

        Returns JSON with structure:
        {
          "<input_curie>": {
            "preferred_id": {"identifier": str, "label": str},
            "equivalent_identifiers": [{"identifier": str, "label": str, "taxa": [str]}],
            "equivalent_identifier_count": int,
            "types": [str],
            "information_content": float,
            "taxa": [str]
          }
        }
        A null value for a CURIE means it was not recognized by the normalization service.

        Error responses:
        - "Error: Rate limit exceeded" — too many requests
        - "Error: Request timed out" — service unavailable
        """
        try:
            params: dict = {
                "curie": curies,
                "conflate": conflate,
                "drug_chemical_conflate": drug_chemical_conflate,
                "description": include_descriptions,
                "include_taxa": include_taxa,
            }

            raw: dict = await make_node_normalization_request(
                "/get_normalized_nodes", params=params
            )

            output = {}
            for input_curie, node in raw.items():
                if node is None:
                    output[input_curie] = None
                    continue

                equiv_ids = node.get("equivalent_identifiers", [])
                total_count = len(equiv_ids)
                if limit_equivalent_ids and limit_equivalent_ids > 0:
                    equiv_ids = equiv_ids[:limit_equivalent_ids]

                entry: dict = {
                    "preferred_id": node.get("id"),
                    "equivalent_identifiers": equiv_ids,
                    "equivalent_identifier_count": total_count,
                    "types": node.get("type", []),
                    "information_content": node.get("information_content"),
                }
                if include_taxa and node.get("taxa"):
                    entry["taxa"] = node["taxa"]
                if limit_equivalent_ids and total_count > limit_equivalent_ids:
                    entry["equivalent_identifiers_truncated"] = True

                output[input_curie] = entry

            return json.dumps(output, indent=2)

        except Exception as e:
            return handle_api_error(e)
