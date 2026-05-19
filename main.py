from translator_mcp.app import mcp

if __name__ == "__main__":
    import os
    port_env = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")
    if port_env:
        mcp.run(transport="http", host="0.0.0.0", port=int(port_env))
    else:
        mcp.run(transport="stdio")
