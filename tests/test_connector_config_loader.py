"""Tests for YAML/JSON connector config loader."""

from __future__ import annotations

import json

import pytest
import yaml

from fim_one.core.tool.connector.config_loader import (
    ConfigValidationError,
    ConnectorConfig,
    config_to_connector,
    detect_format,
    get_config_template,
    parse_connector_config,
)


# ---------------------------------------------------------------------------
# Fixtures — sample configs
# ---------------------------------------------------------------------------

SALESFORCE_YAML = """\
name: Salesforce CRM
description: Manage Salesforce contacts, leads, and opportunities
icon: salesforce
base_url: https://login.salesforce.com
auth_type: oauth2

actions:
  - name: get_contacts
    description: Retrieve contacts matching a filter
    method: GET
    path: /services/data/v58.0/query
    parameters:
      - name: query
        type: string
        required: true
        description: SOQL query string
        semantic_tag: query
    response_mapping:
      output: records

  - name: create_lead
    description: Create a new lead record
    method: POST
    path: /services/data/v58.0/sobjects/Lead
    parameters:
      - name: FirstName
        type: string
        description: Lead's first name
        semantic_tag: name
      - name: LastName
        type: string
        required: true
        semantic_tag: name
      - name: Email
        type: string
        semantic_tag: email
        pii: true
"""

SALESFORCE_JSON = json.dumps(
    {
        "name": "Salesforce CRM",
        "description": "Manage Salesforce contacts, leads, and opportunities",
        "icon": "salesforce",
        "base_url": "https://login.salesforce.com",
        "auth_type": "oauth2",
        "actions": [
            {
                "name": "get_contacts",
                "description": "Retrieve contacts matching a filter",
                "method": "GET",
                "path": "/services/data/v58.0/query",
                "parameters": [
                    {
                        "name": "query",
                        "type": "string",
                        "required": True,
                        "description": "SOQL query string",
                        "semantic_tag": "query",
                    }
                ],
                "response_mapping": {"output": "records"},
            },
            {
                "name": "create_lead",
                "description": "Create a new lead record",
                "method": "POST",
                "path": "/services/data/v58.0/sobjects/Lead",
                "parameters": [
                    {
                        "name": "FirstName",
                        "type": "string",
                        "description": "Lead's first name",
                        "semantic_tag": "name",
                    },
                    {
                        "name": "LastName",
                        "type": "string",
                        "required": True,
                        "semantic_tag": "name",
                    },
                    {
                        "name": "Email",
                        "type": "string",
                        "semantic_tag": "email",
                        "pii": True,
                    },
                ],
            },
        ],
    }
)

MINIMAL_YAML = """\
name: Minimal Connector
"""

YAML_WITH_ENUM = """\
name: Priority API
base_url: https://api.example.com
actions:
  - name: set_priority
    method: POST
    path: /priority
    parameters:
      - name: level
        type: string
        required: true
        enum:
          - low
          - medium
          - high
"""

YAML_WITH_DEFAULTS = """\
name: Default Test
base_url: https://api.example.com
actions:
  - name: search
    method: GET
    path: /search
    parameters:
      - name: query
        type: string
        required: true
      - name: limit
        type: integer
        default: 10
"""

YAML_WITH_AUTH_CONFIG = """\
name: Authenticated API
base_url: https://api.example.com
auth_type: api_key
auth_config:
  header_name: X-API-Key
"""


# ---------------------------------------------------------------------------
# Tests — Format detection
# ---------------------------------------------------------------------------


class TestFormatDetection:
    def test_json_object(self) -> None:
        assert detect_format('{"name": "test"}') == "json"

    def test_json_array(self) -> None:
        assert detect_format('[{"name": "test"}]') == "json"

    def test_json_with_whitespace(self) -> None:
        assert detect_format('  \n  {"name": "test"}') == "json"

    def test_yaml_basic(self) -> None:
        assert detect_format("name: test\ndescription: foo") == "yaml"

    def test_yaml_with_doc_start(self) -> None:
        assert detect_format("---\nname: test") == "yaml"

    def test_empty_string(self) -> None:
        # Empty string is not JSON-like, defaults to yaml
        assert detect_format("") == "yaml"


# ---------------------------------------------------------------------------
# Tests — YAML parsing
# ---------------------------------------------------------------------------


class TestYAMLParsing:
    def test_salesforce_yaml(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        assert config.name == "Salesforce CRM"
        assert config.description == "Manage Salesforce contacts, leads, and opportunities"
        assert config.icon == "salesforce"
        assert config.base_url == "https://login.salesforce.com"
        assert config.auth_type == "oauth2"
        assert len(config.actions) == 2

    def test_action_details(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        get_contacts = config.actions[0]
        assert get_contacts.name == "get_contacts"
        assert get_contacts.method == "GET"
        assert get_contacts.path == "/services/data/v58.0/query"
        assert len(get_contacts.parameters) == 1
        assert get_contacts.parameters[0].name == "query"
        assert get_contacts.parameters[0].required is True

    def test_response_mapping(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        get_contacts = config.actions[0]
        assert get_contacts.response_mapping == {"output": "records"}

    def test_minimal_yaml(self) -> None:
        config = parse_connector_config(MINIMAL_YAML, format="yaml")
        assert config.name == "Minimal Connector"
        assert config.actions == []
        assert config.auth_type == "none"

    def test_auto_format_yaml(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="auto")
        assert config.name == "Salesforce CRM"

    def test_yaml_with_doc_start(self) -> None:
        yaml_text = "---\nname: Test Connector\n"
        config = parse_connector_config(yaml_text, format="auto")
        assert config.name == "Test Connector"


# ---------------------------------------------------------------------------
# Tests — JSON parsing
# ---------------------------------------------------------------------------


class TestJSONParsing:
    def test_salesforce_json(self) -> None:
        config = parse_connector_config(SALESFORCE_JSON, format="json")
        assert config.name == "Salesforce CRM"
        assert len(config.actions) == 2

    def test_auto_format_json(self) -> None:
        config = parse_connector_config(SALESFORCE_JSON, format="auto")
        assert config.name == "Salesforce CRM"

    def test_minimal_json(self) -> None:
        config = parse_connector_config('{"name": "Test"}', format="json")
        assert config.name == "Test"
        assert config.actions == []


# ---------------------------------------------------------------------------
# Tests — Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_empty_config(self) -> None:
        with pytest.raises(ConfigValidationError, match="empty"):
            parse_connector_config("", format="yaml")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ConfigValidationError, match="empty"):
            parse_connector_config("   \n  ", format="yaml")

    def test_missing_name(self) -> None:
        with pytest.raises(ConfigValidationError, match="name"):
            parse_connector_config("description: foo", format="yaml")

    def test_empty_name(self) -> None:
        with pytest.raises(ConfigValidationError, match="name"):
            parse_connector_config('name: ""', format="yaml")

    def test_name_too_long(self) -> None:
        with pytest.raises(ConfigValidationError, match="200 characters"):
            parse_connector_config(f"name: {'A' * 201}", format="yaml")

    def test_invalid_json(self) -> None:
        with pytest.raises(ConfigValidationError, match="Invalid JSON"):
            parse_connector_config("{invalid", format="json")

    def test_invalid_yaml(self) -> None:
        with pytest.raises(ConfigValidationError, match="Invalid YAML"):
            parse_connector_config(":\n  :\n    - :\n  : [", format="yaml")

    def test_scalar_yaml(self) -> None:
        with pytest.raises(ConfigValidationError, match="mapping"):
            parse_connector_config("just a string", format="yaml")

    def test_list_yaml(self) -> None:
        with pytest.raises(ConfigValidationError, match="mapping"):
            parse_connector_config("- item1\n- item2", format="yaml")

    def test_invalid_format(self) -> None:
        with pytest.raises(ConfigValidationError, match="Unsupported format"):
            parse_connector_config("name: test", format="xml")

    def test_duplicate_action_names(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: do_thing
    path: /a
  - name: do_thing
    path: /b
"""
        with pytest.raises(ConfigValidationError, match="duplicate action name"):
            parse_connector_config(yaml_text, format="yaml")

    def test_duplicate_parameter_names(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - name: query
        type: string
      - name: query
        type: integer
"""
        with pytest.raises(ConfigValidationError, match="duplicate parameter name"):
            parse_connector_config(yaml_text, format="yaml")

    def test_action_missing_name(self) -> None:
        yaml_text = """\
name: Test
actions:
  - method: GET
    path: /foo
"""
        with pytest.raises(ConfigValidationError, match="actions\\[0\\].*name"):
            parse_connector_config(yaml_text, format="yaml")

    def test_action_name_too_long(self) -> None:
        yaml_text = f"""\
name: Test
actions:
  - name: {'a' * 201}
    path: /foo
"""
        with pytest.raises(ConfigValidationError, match="200 characters"):
            parse_connector_config(yaml_text, format="yaml")

    def test_invalid_method(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: bad_method
    method: INVALID
    path: /foo
"""
        with pytest.raises(ConfigValidationError, match="method"):
            parse_connector_config(yaml_text, format="yaml")

    def test_parameter_invalid_type(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - name: query
        type: bigint
"""
        with pytest.raises(ConfigValidationError, match="type.*must be one of"):
            parse_connector_config(yaml_text, format="yaml")

    def test_parameter_missing_name(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - type: string
"""
        with pytest.raises(ConfigValidationError, match="parameters\\[0\\].*name"):
            parse_connector_config(yaml_text, format="yaml")

    def test_actions_not_list(self) -> None:
        yaml_text = """\
name: Test
actions: not_a_list
"""
        with pytest.raises(ConfigValidationError, match="actions.*must be a list"):
            parse_connector_config(yaml_text, format="yaml")

    def test_base_url_too_long(self) -> None:
        yaml_text = f"""\
name: Test
base_url: https://{'x' * 500}.com
"""
        with pytest.raises(ConfigValidationError, match="base_url.*500 characters"):
            parse_connector_config(yaml_text, format="yaml")

    def test_path_too_long(self) -> None:
        yaml_text = f"""\
name: Test
actions:
  - name: test_action
    path: /{'x' * 500}
"""
        with pytest.raises(ConfigValidationError, match="path.*500 characters"):
            parse_connector_config(yaml_text, format="yaml")


# ---------------------------------------------------------------------------
# Tests — Config-to-Connector conversion
# ---------------------------------------------------------------------------


class TestConfigToConnector:
    def test_basic_conversion(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")

        assert connector.user_id == "user-123"
        assert connector.name == "Salesforce CRM"
        assert connector.description == "Manage Salesforce contacts, leads, and opportunities"
        assert connector.icon == "salesforce"
        assert connector.base_url == "https://login.salesforce.com"
        assert connector.auth_type == "oauth2"
        assert connector.type == "api"
        assert connector.status == "draft"
        assert connector.visibility == "personal"
        assert len(actions) == 2

    def test_connector_has_uuid(self) -> None:
        config = parse_connector_config(MINIMAL_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert connector.id is not None
        assert len(connector.id) == 36  # UUID format

    def test_action_linked_to_connector(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        for action in actions:
            assert action.connector_id == connector.id

    def test_action_has_uuid(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        for action in actions:
            assert action.id is not None
            assert len(action.id) == 36

    def test_no_actions(self) -> None:
        config = parse_connector_config(MINIMAL_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert actions == []

    def test_auto_requires_confirmation_get(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        assert get_action.requires_confirmation is False

    def test_auto_requires_confirmation_post(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        post_action = next(a for a in actions if a.name == "create_lead")
        assert post_action.requires_confirmation is True

    def test_explicit_requires_confirmation_override(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: safe_post
    method: POST
    path: /safe
    requires_confirmation: false
"""
        config = parse_connector_config(yaml_text, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert actions[0].requires_confirmation is False

    def test_response_mapping_to_extract(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        assert get_action.response_extract == "records"

    def test_no_response_mapping(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        create_action = next(a for a in actions if a.name == "create_lead")
        assert create_action.response_extract is None

    def test_auth_config_preserved(self) -> None:
        config = parse_connector_config(YAML_WITH_AUTH_CONFIG, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert connector.auth_config == {"header_name": "X-API-Key"}


# ---------------------------------------------------------------------------
# Tests — Parameters mapping
# ---------------------------------------------------------------------------


class TestParametersMapping:
    def test_parameters_schema_structure(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        schema = get_action.parameters_schema
        assert schema is not None
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_parameter_type_mapping(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        assert get_action.parameters_schema["properties"]["query"]["type"] == "string"

    def test_parameter_description(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        assert get_action.parameters_schema["properties"]["query"]["description"] == "SOQL query string"

    def test_no_parameters_gives_none(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: health_check
    method: GET
    path: /health
"""
        config = parse_connector_config(yaml_text, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert actions[0].parameters_schema is None

    def test_enum_values_preserved(self) -> None:
        config = parse_connector_config(YAML_WITH_ENUM, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        schema = actions[0].parameters_schema
        assert schema["properties"]["level"]["enum"] == ["low", "medium", "high"]

    def test_default_values_preserved(self) -> None:
        config = parse_connector_config(YAML_WITH_DEFAULTS, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        schema = actions[0].parameters_schema
        assert schema["properties"]["limit"]["default"] == 10

    def test_required_field_tracking(self) -> None:
        config = parse_connector_config(YAML_WITH_DEFAULTS, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        schema = actions[0].parameters_schema
        assert "query" in schema["required"]
        assert "limit" not in schema.get("required", [])

    def test_multiple_required_params(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - name: query
        type: string
        required: true
      - name: index
        type: string
        required: true
      - name: limit
        type: integer
"""
        config = parse_connector_config(yaml_text, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        schema = actions[0].parameters_schema
        assert set(schema["required"]) == {"query", "index"}


# ---------------------------------------------------------------------------
# Tests — Semantic tag preservation
# ---------------------------------------------------------------------------


class TestSemanticTags:
    def test_semantic_tag_in_schema(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        get_action = next(a for a in actions if a.name == "get_contacts")
        assert get_action.parameters_schema["properties"]["query"].get("x-semantic-tag") == "query"

    def test_pii_flag_in_schema(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        create_action = next(a for a in actions if a.name == "create_lead")
        email_prop = create_action.parameters_schema["properties"]["Email"]
        assert email_prop.get("x-pii") is True
        assert email_prop.get("x-semantic-tag") == "email"

    def test_no_semantic_tag_omitted(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - name: query
        type: string
"""
        config = parse_connector_config(yaml_text, format="yaml")
        connector, actions = config_to_connector(config, user_id="user-123")
        schema = actions[0].parameters_schema
        assert "x-semantic-tag" not in schema["properties"]["query"]
        assert "x-pii" not in schema["properties"]["query"]

    def test_semantic_tag_on_dataclass(self) -> None:
        config = parse_connector_config(SALESFORCE_YAML, format="yaml")
        create_lead = config.actions[1]
        assert create_lead.parameters[0].semantic_tag == "name"  # FirstName
        assert create_lead.parameters[2].semantic_tag == "email"  # Email
        assert create_lead.parameters[2].pii is True


# ---------------------------------------------------------------------------
# Tests — Template generation
# ---------------------------------------------------------------------------


class TestTemplateGeneration:
    def test_yaml_template_is_valid(self) -> None:
        template = get_config_template(format="yaml")
        assert isinstance(template, str)
        assert len(template) > 100
        # The template should be parseable YAML
        parsed = yaml.safe_load(template)
        assert isinstance(parsed, dict)
        assert "name" in parsed
        assert "actions" in parsed

    def test_json_template_is_valid(self) -> None:
        template = get_config_template(format="json")
        assert isinstance(template, str)
        assert len(template) > 100
        # The template should be parseable JSON
        parsed = json.loads(template)
        assert isinstance(parsed, dict)
        assert "name" in parsed
        assert "actions" in parsed

    def test_yaml_template_parseable_as_config(self) -> None:
        template = get_config_template(format="yaml")
        config = parse_connector_config(template, format="yaml")
        assert config.name == "My API Service"
        assert len(config.actions) > 0

    def test_json_template_parseable_as_config(self) -> None:
        template = get_config_template(format="json")
        config = parse_connector_config(template, format="json")
        assert config.name == "My API Service"
        assert len(config.actions) > 0

    def test_yaml_template_default(self) -> None:
        template = get_config_template()
        # Default is YAML
        assert "name:" in template
        assert "{" not in template.split("\n")[0]

    def test_yaml_template_has_comments(self) -> None:
        template = get_config_template(format="yaml")
        assert "#" in template  # Should have YAML comments

    def test_template_round_trip(self) -> None:
        """The template should parse and convert to ORM without errors."""
        for fmt in ("yaml", "json"):
            template = get_config_template(format=fmt)
            config = parse_connector_config(template, format=fmt)
            connector, actions = config_to_connector(config, user_id="test-user")
            assert connector.name == "My API Service"
            assert len(actions) > 0


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_method_case_insensitive(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    method: get
    path: /search
"""
        config = parse_connector_config(yaml_text, format="yaml")
        assert config.actions[0].method == "GET"

    def test_name_whitespace_stripped(self) -> None:
        yaml_text = """\
name: "  My Connector  "
"""
        config = parse_connector_config(yaml_text, format="yaml")
        assert config.name == "My Connector"

    def test_action_name_whitespace_stripped(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: "  my_action  "
    path: /foo
"""
        config = parse_connector_config(yaml_text, format="yaml")
        assert config.actions[0].name == "my_action"

    def test_parameter_name_whitespace_stripped(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: search
    path: /search
    parameters:
      - name: "  query  "
        type: string
"""
        config = parse_connector_config(yaml_text, format="yaml")
        assert config.actions[0].parameters[0].name == "query"

    def test_many_actions(self) -> None:
        actions_yaml = "\n".join(
            f"  - name: action_{i}\n    path: /action/{i}" for i in range(50)
        )
        yaml_text = f"name: Bulk Test\nactions:\n{actions_yaml}"
        config = parse_connector_config(yaml_text, format="yaml")
        assert len(config.actions) == 50

    def test_all_parameter_types(self) -> None:
        yaml_text = """\
name: Test
actions:
  - name: all_types
    path: /test
    parameters:
      - name: s
        type: string
      - name: i
        type: integer
      - name: n
        type: number
      - name: b
        type: boolean
      - name: a
        type: array
      - name: o
        type: object
"""
        config = parse_connector_config(yaml_text, format="yaml")
        types = [p.type for p in config.actions[0].parameters]
        assert types == ["string", "integer", "number", "boolean", "array", "object"]

    def test_all_http_methods(self) -> None:
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        actions_yaml = "\n".join(
            f"  - name: action_{m.lower()}\n    method: {m}\n    path: /test"
            for m in methods
        )
        yaml_text = f"name: Test\nactions:\n{actions_yaml}"
        config = parse_connector_config(yaml_text, format="yaml")
        parsed_methods = [a.method for a in config.actions]
        assert parsed_methods == methods

    def test_request_body_template_preserved(self) -> None:
        json_text = json.dumps({
            "name": "Test",
            "actions": [
                {
                    "name": "create",
                    "method": "POST",
                    "path": "/items",
                    "request_body_template": {
                        "type": "{{type}}",
                        "data": {"key": "{{value}}"},
                    },
                }
            ],
        })
        config = parse_connector_config(json_text, format="json")
        connector, actions = config_to_connector(config, user_id="user-123")
        assert actions[0].request_body_template == {
            "type": "{{type}}",
            "data": {"key": "{{value}}"},
        }

    def test_multiple_validation_errors_collected(self) -> None:
        """Multiple errors are reported at once, not one at a time."""
        yaml_text = """\
description: No name here
actions:
  - method: GET
    path: /foo
"""
        with pytest.raises(ConfigValidationError) as exc_info:
            parse_connector_config(yaml_text, format="yaml")
        assert len(exc_info.value.errors) >= 2  # missing name + missing action name

    def test_json_with_comments_fails(self) -> None:
        """JSON does not support comments; verify clean error."""
        with pytest.raises(ConfigValidationError, match="Invalid JSON"):
            parse_connector_config('{\n// comment\n"name": "test"\n}', format="json")
