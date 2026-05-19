from translator_mcp.tools.get_curie_identifiers import register_get_curie_identifiers
from translator_mcp.tools.get_normalized_nodes import register_get_normalized_nodes
from translator_mcp.tools.query_knowledge_graph import register_query_knowledge_graph


def register_tools(mcp) -> None:
    register_get_curie_identifiers(mcp)
    register_get_normalized_nodes(mcp)
    register_query_knowledge_graph(mcp)
