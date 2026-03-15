"""Built-in connector templates (API type only).

These are hardcoded template definitions that serve as starting points for
users creating new API connectors.  They are NOT stored in the database --
the API returns them from memory and allows creating a real ``Connector``
row (with its ``ConnectorAction`` children) from any template via
``POST /api/connector-templates/{id}/create``.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Template definitions — API type only
# ---------------------------------------------------------------------------

CONNECTOR_TEMPLATES: list[dict[str, Any]] = [
    # ── 1. REST API (Bearer Auth) ──────────────────────────────────────
    {
        "id": "rest-bearer",
        "name": "REST API (Bearer Auth)",
        "description": "Generic REST API connector with Bearer token authentication and sample CRUD actions",
        "icon": "KeyRound",
        "category": "api",
        "blueprint": {
            "type": "api",
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "auth_config": {
                "token_prefix": "Bearer",
            },
            "actions": [
                {
                    "name": "List Items",
                    "description": "Retrieve a paginated list of items",
                    "method": "GET",
                    "path": "/items",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer", "description": "Page number (1-based)"},
                            "limit": {"type": "integer", "description": "Items per page (max 100)"},
                        },
                    },
                },
                {
                    "name": "Get Item",
                    "description": "Retrieve a single item by its ID",
                    "method": "GET",
                    "path": "/items/{id}",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Item ID"},
                        },
                        "required": ["id"],
                    },
                },
                {
                    "name": "Create Item",
                    "description": "Create a new item",
                    "method": "POST",
                    "path": "/items",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Item name"},
                            "description": {"type": "string", "description": "Item description"},
                        },
                        "required": ["name"],
                    },
                    "request_body_template": {
                        "name": "{{name}}",
                        "description": "{{description}}",
                    },
                },
                {
                    "name": "Update Item",
                    "description": "Update an existing item",
                    "method": "PUT",
                    "path": "/items/{id}",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Item ID"},
                            "name": {"type": "string", "description": "New item name"},
                            "description": {"type": "string", "description": "New item description"},
                        },
                        "required": ["id"],
                    },
                    "request_body_template": {
                        "name": "{{name}}",
                        "description": "{{description}}",
                    },
                },
                {
                    "name": "Delete Item",
                    "description": "Delete an item by its ID",
                    "method": "DELETE",
                    "path": "/items/{id}",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Item ID"},
                        },
                        "required": ["id"],
                    },
                },
            ],
        },
    },
    # ── 2. REST API (API Key) ──────────────────────────────────────────
    {
        "id": "rest-api-key",
        "name": "REST API (API Key)",
        "description": "Generic REST API connector with API key header authentication and sample actions",
        "icon": "KeyRound",
        "category": "api",
        "blueprint": {
            "type": "api",
            "base_url": "https://api.example.com",
            "auth_type": "api_key",
            "auth_config": {
                "header_name": "X-API-Key",
            },
            "actions": [
                {
                    "name": "List Resources",
                    "description": "List all available resources",
                    "method": "GET",
                    "path": "/resources",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer", "description": "Page number"},
                            "per_page": {"type": "integer", "description": "Results per page"},
                            "sort": {"type": "string", "description": "Sort field"},
                            "order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort order"},
                        },
                    },
                },
                {
                    "name": "Get Resource",
                    "description": "Get a specific resource by ID",
                    "method": "GET",
                    "path": "/resources/{id}",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Resource ID"},
                        },
                        "required": ["id"],
                    },
                },
                {
                    "name": "Search Resources",
                    "description": "Search resources with a query string",
                    "method": "GET",
                    "path": "/resources/search",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "q": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "description": "Maximum results"},
                        },
                        "required": ["q"],
                    },
                },
            ],
        },
    },
    # ── 3. Webhook Receiver ────────────────────────────────────────────
    {
        "id": "webhook-receiver",
        "name": "Webhook Receiver",
        "description": "Incoming webhook pattern for receiving POST events from external services",
        "icon": "Globe",
        "category": "api",
        "blueprint": {
            "type": "api",
            "base_url": "https://hooks.example.com",
            "auth_type": "none",
            "auth_config": {},
            "actions": [
                {
                    "name": "Receive Event",
                    "description": "Handle an incoming webhook event payload",
                    "method": "POST",
                    "path": "/webhook",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "event_type": {"type": "string", "description": "Type of the webhook event"},
                            "payload": {"type": "object", "description": "Event payload data"},
                        },
                        "required": ["event_type"],
                    },
                    "request_body_template": {
                        "event": "{{event_type}}",
                        "data": "{{payload}}",
                    },
                },
                {
                    "name": "Verify Webhook",
                    "description": "Respond to a webhook verification challenge",
                    "method": "GET",
                    "path": "/webhook",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "challenge": {"type": "string", "description": "Verification challenge token"},
                        },
                    },
                },
            ],
        },
    },
    # ── 4. GitHub API ──────────────────────────────────────────────────
    {
        "id": "github-api",
        "name": "GitHub API",
        "description": "Pre-configured connector for GitHub REST API v3 with common repository and issue actions",
        "icon": "GitBranch",
        "category": "api",
        "blueprint": {
            "type": "api",
            "base_url": "https://api.github.com",
            "auth_type": "bearer",
            "auth_config": {
                "token_prefix": "Bearer",
            },
            "actions": [
                {
                    "name": "List Repositories",
                    "description": "List repositories for the authenticated user",
                    "method": "GET",
                    "path": "/user/repos",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["all", "owner", "public", "private", "member"],
                                "description": "Type of repositories to list",
                            },
                            "sort": {
                                "type": "string",
                                "enum": ["created", "updated", "pushed", "full_name"],
                                "description": "Sort field",
                            },
                            "per_page": {"type": "integer", "description": "Results per page (max 100)"},
                            "page": {"type": "integer", "description": "Page number"},
                        },
                    },
                    "response_extract": "[].{name: name, full_name: full_name, description: description, html_url: html_url, stargazers_count: stargazers_count}",
                },
                {
                    "name": "Get Repository",
                    "description": "Get detailed information about a specific repository",
                    "method": "GET",
                    "path": "/repos/{owner}/{repo}",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "owner": {"type": "string", "description": "Repository owner (username or org)"},
                            "repo": {"type": "string", "description": "Repository name"},
                        },
                        "required": ["owner", "repo"],
                    },
                },
                {
                    "name": "List Issues",
                    "description": "List issues in a repository",
                    "method": "GET",
                    "path": "/repos/{owner}/{repo}/issues",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "owner": {"type": "string", "description": "Repository owner"},
                            "repo": {"type": "string", "description": "Repository name"},
                            "state": {
                                "type": "string",
                                "enum": ["open", "closed", "all"],
                                "description": "Issue state filter",
                            },
                            "labels": {"type": "string", "description": "Comma-separated label names"},
                            "per_page": {"type": "integer", "description": "Results per page"},
                        },
                        "required": ["owner", "repo"],
                    },
                    "response_extract": "[].{number: number, title: title, state: state, user: user.login, labels: labels[].name}",
                },
                {
                    "name": "Create Issue",
                    "description": "Create a new issue in a repository",
                    "method": "POST",
                    "path": "/repos/{owner}/{repo}/issues",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "owner": {"type": "string", "description": "Repository owner"},
                            "repo": {"type": "string", "description": "Repository name"},
                            "title": {"type": "string", "description": "Issue title"},
                            "body": {"type": "string", "description": "Issue body (Markdown)"},
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Labels to assign",
                            },
                        },
                        "required": ["owner", "repo", "title"],
                    },
                    "request_body_template": {
                        "title": "{{title}}",
                        "body": "{{body}}",
                        "labels": "{{labels}}",
                    },
                },
                {
                    "name": "Search Code",
                    "description": "Search for code across GitHub repositories",
                    "method": "GET",
                    "path": "/search/code",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "q": {"type": "string", "description": "Search query (GitHub search syntax)"},
                            "per_page": {"type": "integer", "description": "Results per page"},
                            "page": {"type": "integer", "description": "Page number"},
                        },
                        "required": ["q"],
                    },
                    "response_extract": "items[].{name: name, path: path, repository: repository.full_name, html_url: html_url}",
                },
            ],
        },
    },
    # ── 5. OpenAI API ──────────────────────────────────────────────────
    {
        "id": "openai-api",
        "name": "OpenAI API",
        "description": "Pre-configured connector for the OpenAI API with chat completion and model listing actions",
        "icon": "BrainCircuit",
        "category": "api",
        "blueprint": {
            "type": "api",
            "base_url": "https://api.openai.com/v1",
            "auth_type": "bearer",
            "auth_config": {
                "token_prefix": "Bearer",
            },
            "actions": [
                {
                    "name": "Chat Completion",
                    "description": "Create a chat completion using the OpenAI API",
                    "method": "POST",
                    "path": "/chat/completions",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Model ID (e.g. gpt-4o, gpt-4o-mini)",
                            },
                            "messages": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                        "content": {"type": "string"},
                                    },
                                    "required": ["role", "content"],
                                },
                                "description": "List of messages in the conversation",
                            },
                            "temperature": {
                                "type": "number",
                                "description": "Sampling temperature (0 to 2)",
                            },
                            "max_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens to generate",
                            },
                        },
                        "required": ["model", "messages"],
                    },
                    "request_body_template": {
                        "model": "{{model}}",
                        "messages": "{{messages}}",
                        "temperature": "{{temperature}}",
                        "max_tokens": "{{max_tokens}}",
                    },
                    "response_extract": "choices[0].message.content",
                },
                {
                    "name": "List Models",
                    "description": "List all available models in your OpenAI account",
                    "method": "GET",
                    "path": "/models",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                    },
                    "response_extract": "data[].{id: id, owned_by: owned_by}",
                },
                {
                    "name": "Create Embedding",
                    "description": "Create text embeddings using OpenAI embedding models",
                    "method": "POST",
                    "path": "/embeddings",
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Embedding model (e.g. text-embedding-3-small)",
                            },
                            "input": {
                                "type": "string",
                                "description": "Text to embed",
                            },
                        },
                        "required": ["model", "input"],
                    },
                    "request_body_template": {
                        "model": "{{model}}",
                        "input": "{{input}}",
                    },
                    "response_extract": "data[0].embedding",
                },
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> list[dict[str, Any]]:
    """Return all built-in connector templates."""
    return CONNECTOR_TEMPLATES


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return a single template by ID, or None."""
    for tmpl in CONNECTOR_TEMPLATES:
        if tmpl["id"] == template_id:
            return tmpl
    return None
