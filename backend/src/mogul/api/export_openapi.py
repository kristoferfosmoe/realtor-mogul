"""Print the OpenAPI schema; the web app generates its TypeScript types from it."""

import json

from mogul.api.app import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
