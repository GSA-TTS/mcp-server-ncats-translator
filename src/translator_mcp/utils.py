import httpx

NAME_RESOLUTION_BASE_URL = "https://name-resolution-sri.renci.org"
NODE_NORMALIZATION_BASE_URL = "https://nodenormalization-sri.renci.org"
ARS_SUBMIT_BASE_URL = "https://ars-prod.transltr.io/ars/api"
ARS_STATUS_BASE_URL = "https://ars-prod.transltr.io/ars/api"
ARS_RESULTS_BASE_URL = "https://ars-prod.transltr.io/ars/api"


async def make_api_request(
    base_url: str,
    endpoint: str,
    method: str = "GET",
    **kwargs,
) -> dict | list:
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            f"{base_url}{endpoint}",
            timeout=30.0,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


async def make_name_resolution_request(
    endpoint: str,
    method: str = "GET",
    **kwargs,
) -> dict | list:
    return await make_api_request(NAME_RESOLUTION_BASE_URL, endpoint, method, **kwargs)


async def make_node_normalization_request(
    endpoint: str,
    method: str = "GET",
    **kwargs,
) -> dict | list:
    return await make_api_request(NODE_NORMALIZATION_BASE_URL, endpoint, method, **kwargs)


async def make_ars_submit_request(endpoint: str, **kwargs) -> dict:
    return await make_api_request(ARS_SUBMIT_BASE_URL, endpoint, method="POST", **kwargs)


async def make_ars_status_request(endpoint: str, **kwargs) -> dict:
    # ARS status calls can be slow while agents are running; use a longer timeout
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ARS_STATUS_BASE_URL}{endpoint}",
            timeout=60.0,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


async def make_ars_results_request(endpoint: str, **kwargs) -> dict:
    # Child result payloads can be large; allow extra time
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ARS_RESULTS_BASE_URL}{endpoint}",
            timeout=60.0,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


def handle_api_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 404:
            return "Error: Resource not found."
        elif e.response.status_code == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        return f"Error: API request failed with status {e.response.status_code}: {e.response.text}"
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    return f"Error: Unexpected error: {type(e).__name__}: {e}"
