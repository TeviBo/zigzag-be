from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ZigZag API Gateway", docs_url=None, redoc_url=None)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <!-- Dark Mode Theme -->
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-themes@3.0.0/themes/3.x/theme-material.css">
    <title>ZigZag Unified API</title>
    </head>
    <body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    const ui = SwaggerUIBundle({
        urls: [
            {url: "http://localhost:8001/openapi.json", name: "Product Service"},
            {url: "http://localhost:8002/openapi.json", name: "Cart Service"},
            {url: "http://localhost:8003/openapi.json", "name": "Order & Checkout Service"},
            {url: "http://localhost:8004/openapi.json", "name": "Auth Service"},
            {url: "http://localhost:8005/openapi.json", "name": "Notification Service"}
        ],
        dom_id: '#swagger-ui',
        presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIStandalonePreset
        ],
        layout: "StandaloneLayout",
        deepLinking: true
    })
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Welcome to ZigZag API Gateway. Go to /docs for Swagger UI"}
