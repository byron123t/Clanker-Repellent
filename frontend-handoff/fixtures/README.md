# Fixed sample responses

`responses.json` contains saved synthetic responses for the frontend's GET requests.
Its `scenarios` maps request URLs to response indexes. JSON responses are stored as JSON;
binary download bodies are labeled base64. Query parameter order is normalized by the server.

The data covers seven fictional projects and three response samples, plus empty and error
states. It was exported from the owner's synthetic design dataset. The preview server
returns those saved values without creating or modifying project records.

Use this data as supplied while redesigning `web/`. Its byte positions, sizes, preview
content, and download bytes are consistent. The handoff includes no data-generation tool.
