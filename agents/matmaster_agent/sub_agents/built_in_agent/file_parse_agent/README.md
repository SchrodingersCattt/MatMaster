# parse_file (MCP tool)

This directory contains the **parse_file** implementation with no MatMaster dependencies. It is intended to be migrated to the document parser MCP server.

- **MCP tool name**: `parse_file`
- **Parameter**: `file_url: str`
- **Return**: `{"msg": "..."}`

After migration, register this tool on the document parser server alongside `extract_material_data_from_pdf` and `extract_info_from_webpage`. MatMaster uses it via `document_parser_agent` (DocumentParserAgentName).
