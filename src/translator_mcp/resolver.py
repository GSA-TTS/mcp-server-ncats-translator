"""Shared name-to-CURIE resolution logic used across tools."""

from translator_mcp.utils import make_name_resolution_request, make_node_normalization_request


async def resolve_name_to_curie(name: str, categories: list[str] | None = None) -> tuple[str, str]:
    """Resolve a natural-language name to a canonical CURIE.

    Steps:
    1. Call name resolution to find the top matching CURIE for the name.
    2. Call node normalization to get the canonical (preferred) CURIE for that match.

    Returns a (curie, label) tuple.
    Raises ValueError if no match is found.
    Falls back to the raw name-resolution CURIE if normalization returns null.
    """
    params: dict = {"string": name, "limit": 1, "autocomplete": False}
    if categories:
        params["biolink_type"] = categories

    lookup_results = await make_name_resolution_request("/lookup", params=params)

    if not lookup_results:
        # Retry with autocomplete in case exact match failed
        params["autocomplete"] = True
        lookup_results = await make_name_resolution_request("/lookup", params=params)

    if not lookup_results:
        raise ValueError(
            f"Could not resolve '{name}' to a CURIE. "
            "Try providing the CURIE directly, or check the spelling."
        )

    raw_curie = lookup_results[0]["curie"]
    raw_label = lookup_results[0].get("label", raw_curie)

    # Normalize to get the canonical preferred identifier
    norm_results = await make_node_normalization_request(
        "/get_normalized_nodes", params={"curie": [raw_curie]}
    )
    node = norm_results.get(raw_curie)

    if node and node.get("id"):
        canonical_curie = node["id"]["identifier"]
        canonical_label = node["id"].get("label") or raw_label
        return canonical_curie, canonical_label

    # Normalization returned null — use the raw result
    return raw_curie, raw_label
