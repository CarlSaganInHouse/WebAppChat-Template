"""
Auto-generate canonical Obsidian tools schema from function definitions.

This module generates obsidian_tools.schema.json as the single source of truth
for all tool definitions. It's called on app startup and can be regenerated
anytime tools are added/modified.

Phase 2: Infrastructure layer for canonical schema management.
"""

import json
from datetime import datetime
from pathlib import Path


def build_obsidian_schema(functions_list=None):
    """
    Generate canonical schema from function definitions.
    
    Args:
        functions_list: List of function defs (if None, imports from get_obsidian_functions)
    
    Returns:
        dict: Schema with all tool definitions
    """
    if functions_list is None:
        from obsidian_functions import get_obsidian_functions
        functions_list = get_obsidian_functions()
    
    schema = {
        "version": "2.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "phase": "2-canonical-schema",
        "total_tools": len(functions_list),
        "tools": {}
    }
    
    for func_def in functions_list:
        name = func_def.get("name", "unknown")
        schema["tools"][name] = {
            "name": name,
            "description": func_def.get("description", ""),
            "parameters": func_def.get("parameters", {})
        }
    
    return schema


def save_schema(output_path=None):
    """
    Generate and save schema to JSON file.
    
    Args:
        output_path: Where to save (default: /root/WebAppChat/obsidian_tools.schema.json)
    
    Returns:
        bool: True if successful
    """
    if output_path is None:
        output_path = "/root/WebAppChat/obsidian_tools.schema.json"
    
    try:
        schema = build_obsidian_schema()
        
        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Write with nice formatting
        with open(output_path, 'w') as f:
            json.dump(schema, f, indent=2)
        
        print(f"✅ Schema generated: {output_path}")
        print(f"   Total tools: {schema['total_tools']}")
        print(f"   Generated: {schema['generated_at']}")
        return True
    
    except Exception as e:
        print(f"❌ Error generating schema: {str(e)}")
        return False


def load_schema(schema_path=None):
    """
    Load existing schema from file.
    
    Args:
        schema_path: Path to schema file
    
    Returns:
        dict: Loaded schema or empty dict if not found
    """
    if schema_path is None:
        schema_path = "/root/WebAppChat/obsidian_tools.schema.json"
    
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load schema: {str(e)}")
        return {}


def get_tool_description(tool_name, schema_path=None):
    """
    Retrieve description for a specific tool from schema.
    
    Args:
        tool_name: Name of the tool
        schema_path: Path to schema file (if None, uses default)
    
    Returns:
        str: Description or empty string
    """
    schema = load_schema(schema_path)
    return schema.get("tools", {}).get(tool_name, {}).get("description", "")


def validate_tool_in_schema(tool_name, schema_path=None):
    """
    Check if a tool is defined in the schema.
    
    Args:
        tool_name: Name of the tool
        schema_path: Path to schema file
    
    Returns:
        bool: True if tool exists in schema
    """
    schema = load_schema(schema_path)
    return tool_name in schema.get("tools", {})


if __name__ == "__main__":
    # Run as standalone script: python3 schema_generator.py
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else None
    success = save_schema(output)
    sys.exit(0 if success else 1)
