"""
Integration tests for ToolCallingService centralization.

This test verifies that:
1. ToolCallingService is correctly instantiated in LLMService
2. Tool execution flows through the service
3. Validation, logging, and context updates work end-to-end
4. Both OpenAI and Anthropic flows use the service
"""

import os
import sys
import json
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToolCallingServiceIntegration(unittest.TestCase):
    """Integration tests for the ToolCallingService"""

    @unittest.skip("Requires Flask environment with structlog")
    def test_llm_service_has_tool_service(self):
        """Verify LLMService instantiates ToolCallingService"""
        # Patch verify_tool_result before importing
        with patch("routes.chat_routes.verify_tool_result"):
            from services.llm_service import LLMService
            
            service = LLMService()
            self.assertTrue(hasattr(service, "tool_service"))
            self.assertIsNotNone(service.tool_service)

    @unittest.skip("Requires Flask environment with structlog")
    def test_tool_service_has_all_dependencies(self):
        """Verify ToolCallingService has all dependency functions"""
        with patch("routes.chat_routes.verify_tool_result") as mock_verify:
            from services.llm_service import LLMService
            
            service = LLMService()
            ts = service.tool_service
            
            # Check all dependency functions are set
            self.assertIsNotNone(ts.execute_fn)
            self.assertIsNotNone(ts.verify_fn)
            self.assertIsNotNone(ts.log_fn)
            self.assertIsNotNone(ts.validate_fn)
            self.assertIsNotNone(ts.update_context_fn)

    def test_execute_tool_call_validation(self):
        """Test that validation is called before execution"""
        from services.tool_calling_service import ToolCallingService
        
        mock_execute = Mock(return_value={"success": True})
        mock_validate = Mock(return_value=(False, "Missing required field: content"))
        mock_log = Mock()
        
        ts = ToolCallingService(
            execute_fn=mock_execute,
            validate_fn=mock_validate,
            log_fn=mock_log,
        )
        
        result, status = ts.execute_tool_call(
            tool_call_id="test123",
            function_name="append_to_daily_note",
            function_args={},  # Missing content
            model="gpt-4o",
        )
        
        # Validation should fail
        self.assertEqual(status, "validation_error")
        self.assertIn("Missing required field", result.get("error", ""))
        
        # Execute should NOT have been called
        mock_execute.assert_not_called()
        
        # Log should have been called with validation_error
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        self.assertEqual(call_kwargs["status"], "validation_error")

    def test_execute_tool_call_success(self):
        """Test successful tool execution flow"""
        from services.tool_calling_service import ToolCallingService
        
        mock_execute = Mock(return_value={"success": True, "message": "Note created"})
        mock_validate = Mock(return_value=(True, ""))
        mock_verify = Mock(return_value=("passed", None))
        mock_log = Mock()
        
        ts = ToolCallingService(
            execute_fn=mock_execute,
            validate_fn=mock_validate,
            verify_fn=mock_verify,
            log_fn=mock_log,
        )
        
        result, status = ts.execute_tool_call(
            tool_call_id="test123",
            function_name="create_simple_note",
            function_args={"title": "Test", "content": "Hello", "folder": "Test"},
            model="gpt-4o",
        )
        
        self.assertEqual(status, "success")
        self.assertTrue(result.get("success"))
        
        # All stages should have been called
        mock_validate.assert_called_once()
        mock_execute.assert_called_once()
        mock_verify.assert_called_once()
        mock_log.assert_called_once()

    def test_execute_tool_calls_batch(self):
        """Test batch execution of multiple tool calls"""
        from services.tool_calling_service import ToolCallingService
        
        call_count = [0]
        
        def mock_execute(name, args):
            call_count[0] += 1
            return {"success": True, "call": call_count[0]}
        
        ts = ToolCallingService(
            execute_fn=mock_execute,
            validate_fn=lambda n, a: (True, ""),
        )
        
        tool_calls = [
            {"id": "call1", "function": {"name": "read_note", "arguments": '{"file_path": "test.md"}'}},
            {"id": "call2", "function": {"name": "list_folder_contents", "arguments": '{"folder_name": "Jobs"}'}},
        ]
        
        result_messages = ts.execute_tool_calls_batch(
            tool_calls=tool_calls,
            model="gpt-4o",
        )
        
        self.assertEqual(len(result_messages), 2)
        self.assertEqual(result_messages[0]["tool_call_id"], "call1")
        self.assertEqual(result_messages[1]["tool_call_id"], "call2")
        self.assertEqual(call_count[0], 2)

    def test_execute_anthropic_tool(self):
        """Test Anthropic-style tool execution"""
        from services.tool_calling_service import ToolCallingService
        
        mock_execute = Mock(return_value={"success": True, "files": ["a.md", "b.md"]})
        
        ts = ToolCallingService(
            execute_fn=mock_execute,
            validate_fn=lambda n, a: (True, ""),
        )
        
        # Simulate Anthropic tool_use block
        tool_use_block = Mock()
        tool_use_block.id = "toolu_abc123"
        tool_use_block.name = "list_folder_contents"
        tool_use_block.input = {"folder_name": "Homelab"}
        
        result, tool_id = ts.execute_anthropic_tool(
            tool_use_block=tool_use_block,
            model="claude-sonnet-4-20250514",
        )
        
        self.assertEqual(tool_id, "toolu_abc123")
        self.assertTrue(result.get("success"))
        mock_execute.assert_called_once_with("list_folder_contents", {"folder_name": "Homelab"})

    def test_format_tool_result_for_anthropic(self):
        """Test Anthropic result formatting"""
        from services.tool_calling_service import ToolCallingService
        
        ts = ToolCallingService(execute_fn=lambda n, a: {})
        
        result = ts.format_tool_result_for_anthropic(
            tool_use_id="toolu_xyz",
            result={"success": True, "content": "Note created"}
        )
        
        self.assertEqual(result["role"], "user")
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "tool_result")
        self.assertEqual(result["content"][0]["tool_use_id"], "toolu_xyz")
        
        # Content should be JSON string
        content = json.loads(result["content"][0]["content"])
        self.assertTrue(content["success"])

    @unittest.skip("Requires Flask environment with structlog")
    def test_warn_but_allow_validation(self):
        """Test that uncovered functions are allowed with warning"""
        from tool_schema import validate_tool_call
        
        # Function not in schema should pass with warning
        is_valid, error = validate_tool_call("some_uncovered_function", {"arg": "value"})
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    @unittest.skip("Requires Flask environment with structlog")
    def test_covered_function_validation_fails(self):
        """Test that covered functions with missing required fields fail"""
        from tool_schema import validate_tool_call
        
        # Missing required 'content' field
        is_valid, error = validate_tool_call("append_to_daily_note", {})
        self.assertFalse(is_valid)
        self.assertIn("content", error)


if __name__ == "__main__":
    unittest.main()
