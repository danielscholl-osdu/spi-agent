"""Test MCP array parameter handling."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import MCPStdioTool
from agent_framework._mcp import _get_input_model_from_mcp_tool
from mcp import types


@pytest.mark.asyncio
async def test_mcp_array_parameter_type_mapping():
    """Test that MCP tools with array parameters are correctly mapped to Python list type."""
    # Create a mock MCP tool with an array parameter
    mock_tool = types.Tool(
        name="test_tool",
        description="Test tool with array parameter",
        inputSchema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of items"
                }
            },
            "required": ["items"]
        }
    )

    # Get the input model
    input_model = _get_input_model_from_mcp_tool(mock_tool)

    # Check the field type
    fields = input_model.model_fields
    assert "items" in fields

    # The field should be of type list
    field_info = fields["items"]
    assert field_info.annotation == list

    print(f"✓ Array parameter correctly mapped to Python list type")
    print(f"  Field annotation: {field_info.annotation}")


@pytest.mark.asyncio
async def test_mcp_call_with_array_argument():
    """Test that array arguments are preserved when calling MCP tools."""
    # Create a mock MCP session
    mock_session = AsyncMock()
    mock_call_result = types.CallToolResult(
        content=[types.TextContent(type="text", text="Success")]
    )
    mock_session.call_tool = AsyncMock(return_value=mock_call_result)

    # Create MCP tool with mock session - enable load_tools
    mcp_tool = MCPStdioTool(
        name="test-server",
        command="echo",
        args=["test"],
        session=mock_session,
        load_tools=True,  # Enable tools
        load_prompts=False,
    )

    # Call tool with array argument
    test_items = ["item1", "item2", "item3"]
    await mcp_tool.call_tool("test_tool", items=test_items)

    # Verify the session.call_tool was called with the array
    mock_session.call_tool.assert_called_once()
    call_args = mock_session.call_tool.call_args

    print(f"\n🔍 MCP Session call_tool invoked with:")
    print(f"  Tool name: {call_args[0][0]}")
    print(f"  Arguments: {call_args[1].get('arguments')}")
    print(f"  Arguments type: {type(call_args[1].get('arguments'))}")

    # Check that items is still a list
    arguments = call_args[1].get('arguments')
    assert arguments is not None
    assert "items" in arguments
    assert isinstance(arguments["items"], list)
    assert arguments["items"] == test_items

    print(f"✓ Array argument preserved as list in MCP call")


@pytest.mark.asyncio
async def test_pydantic_model_dump_preserves_arrays():
    """Test that Pydantic model_dump preserves list types."""
    from pydantic import BaseModel, create_model

    # Create a model with a list field
    TestModel = create_model(
        "TestModel",
        items=(list, ...)
    )

    # Create instance with list data
    test_data = ["a", "b", "c"]
    model_instance = TestModel(items=test_data)

    # Dump to dict
    dumped = model_instance.model_dump(exclude_none=True)

    print(f"\n🔍 Pydantic model_dump output:")
    print(f"  Type: {type(dumped)}")
    print(f"  Content: {dumped}")
    print(f"  items type: {type(dumped['items'])}")
    print(f"  items value: {dumped['items']}")

    # Verify list is preserved
    assert isinstance(dumped["items"], list)
    assert dumped["items"] == test_data

    print(f"✓ Pydantic model_dump preserves list type")


@pytest.mark.asyncio
async def test_function_call_parse_arguments_with_array():
    """Test that FunctionCallContent.parse_arguments preserves arrays."""
    from agent_framework._types import FunctionCallContent

    # Test with JSON string containing array
    json_args = '{"items": ["a", "b", "c"]}'
    func_call = FunctionCallContent(
        call_id="test_123",
        name="test_tool",
        arguments=json_args
    )

    parsed = func_call.parse_arguments()

    print(f"\n🔍 FunctionCallContent.parse_arguments:")
    print(f"  Input: {json_args}")
    print(f"  Parsed: {parsed}")
    print(f"  items type: {type(parsed['items'])}")

    assert isinstance(parsed["items"], list)
    assert parsed["items"] == ["a", "b", "c"]

    # Test with dict containing array
    dict_args = {"items": ["x", "y", "z"]}
    func_call2 = FunctionCallContent(
        call_id="test_456",
        name="test_tool",
        arguments=dict_args
    )

    parsed2 = func_call2.parse_arguments()

    print(f"\n🔍 FunctionCallContent with dict input:")
    print(f"  Input: {dict_args}")
    print(f"  Parsed: {parsed2}")
    print(f"  items type: {type(parsed2['items'])}")

    assert isinstance(parsed2["items"], list)
    assert parsed2["items"] == ["x", "y", "z"]

    print(f"✓ parse_arguments preserves array types")


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 70)
        print("Testing MCP Array Parameter Handling")
        print("=" * 70)

        await test_mcp_array_parameter_type_mapping()
        print()
        await test_mcp_call_with_array_argument()
        print()
        await test_pydantic_model_dump_preserves_arrays()
        print()
        await test_function_call_parse_arguments_with_array()

        print("\n" + "=" * 70)
        print("All tests passed! ✓")
        print("=" * 70)

    asyncio.run(run_tests())
