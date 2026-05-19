import os

from fastmcp import FastMCP

from translator_mcp.tools import register_tools

mcp = FastMCP(
    "translator_mcp",
    instructions=(
        "This server provides access to NCATS Translator APIs for biomedical knowledge graph exploration. "
        "It maps natural-language names and synonyms to standardized CURIE identifiers used across Translator services.\n\n"
        "TOOL SELECTION GUIDE:\n"
        "- Resolve a disease/gene/chemical name to a CURIE → translator_get_curie_identifiers\n"
        "- Normalize a CURIE / find equivalent identifiers across ontologies → translator_get_normalized_nodes\n"
        "- Query the knowledge graph with nodes + edges (waits for results) → translator_query_knowledge_graph\n\n"
        "CONVENTIONS:\n"
        "- CURIEs follow the format PREFIX:ID (e.g., MONDO:0005148, NCBIGene:672, CHEBI:15422)\n"
        "- Biolink types use the format 'biolink:EntityType' (e.g., 'biolink:Disease', 'biolink:Gene')\n"
        "- Prefix filters are pipe-separated (e.g., 'MONDO|EFO|HP')\n"
        "- Results are paginated; use offset + limit to page through large result sets\n\n"
        "No authentication required — all endpoints are publicly accessible."
    ),
)

register_tools(mcp)

if __name__ == "__main__":
    port_env = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")
    if port_env:
        mcp.run(transport="http", host="0.0.0.0", port=int(port_env))
    else:
        mcp.run(transport="stdio")
