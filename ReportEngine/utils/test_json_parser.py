"""Test various repair capabilities of RobustJSONParser.

Verify that the parser can handle:
1. Basic markdown package
2. Think about content cleanup
3. Missing comma fix
4. Repair of unbalanced brackets
5. Control character escaping
6. Trailing comma removal"""

import json
import unittest
from json_parser import RobustJSONParser, JSONParseError


class TestRobustJSONParser(unittest.TestCase):
    """Test various repair strategies for robust JSON parsers."""

    def setUp(self):
        """Initialize the parser."""
        self.parser = RobustJSONParser(
            enable_json_repair=False,  # Test local fix first
            enable_llm_repair=False,
        )

    def test_basic_json(self):
        """Test parsing basic legal JSON."""
        json_str = '{"name": "test", "value": 123}'
        result = self.parser.parse(json_str, "basic test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_markdown_wrapped(self):
        """The test parses JSON wrapped in ```json."""
        json_str = """```json
{
  "name": "test",
  "value": 123
}
```"""
        result = self.parser.parse(json_str, "Markdown package test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_thinking_content_removal(self):
        """Test to clear up your thinking."""
        json_str = """<thinking>Let me think about how to construct this JSON</thinking>
{"name": "test",
  "value": 123
}"""
        result = self.parser.parse(json_str, "Thinking About Content Cleanup Testing")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_missing_comma_fix(self):
        """Test fix missing comma."""
        # This is a common case in real-world errors: missing commas between array elements
        json_str = """{
  "totalWords": 40000,
  "globalGuidelines": [
    "重点突出技术红利分配失衡"
    "详略策略：技术创新"
  ],
  "chapters": []
}"""
        result = self.parser.parse(json_str, "Missing comma fix test")
        self.assertEqual(len(result["globalGuidelines"]), 2)

    def test_unbalanced_brackets(self):
        """Test fix for bracket imbalance."""
        # Missing closing bracket
        json_str = """{
  "name": "test",
  "nested": {
    "value": 123
  }
"""  # Missing outermost }
        result = self.parser.parse(json_str, "Bracket imbalance test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["nested"]["value"], 123)

    def test_control_character_escape(self):
        """Test for escaping control characters."""
        # Naked newlines in JSON strings should be escaped
        json_str = """{
  "text": "这是第一行
这是第二行",
  "value": 123
}"""
        result = self.parser.parse(json_str, "Control character escape test")
        # Make sure newlines are handled correctly
        self.assertIn("first line", result["text"])
        self.assertIn("second line", result["text"])

    def test_trailing_comma_removal(self):
        """Test removing trailing commas."""
        json_str = """{
  "name": "test",
  "value": 123,
  "items": [1, 2, 3,],
}"""
        result = self.parser.parse(json_str, "Trailing comma test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(len(result["items"]), 3)

    def test_colon_equals_fix(self):
        """Test fix colon equal sign error."""
        json_str = """{
  "name":= "test",
  "value": 123
}"""
        result = self.parser.parse(json_str, "colon equal sign test")
        self.assertEqual(result["name"], "test")

    def test_extract_first_json(self):
        """The test extracts the first JSON structure from the text."""
        json_str = """Here is some explanatory text, and below is the JSON:
{"name": "test",
  "value": 123
}
There are some other words behind it"""
        result = self.parser.parse(json_str, "Extract JSON test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_unterminated_string_with_json_repair(self):
        """Tests repair of unterminated strings using the json_repair library."""
        # Create a parser with json_repair enabled
        parser_with_repair = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
        )

        # Simulate actual error: unescaped control characters or quotes in string
        json_str = """{
  "template_name": "特定政策报告",
  "selection_reason": "这是测试内容"
}"""
        result = parser_with_repair.parse(json_str, "Unterminated string test")
        # As long as it can be parsed successfully and no error is reported, it will be fine.
        self.assertIsInstance(result, dict)
        self.assertIn("template_name", result)

    def test_array_with_best_match(self):
        """Tests extracting the best matching element from an array."""
        json_str = """[
  {
    "name": "test",
    "value": 123
  },
  {
    "totalWords": 40000,
    "globalGuidelines": ["guide1", "guide2"],
    "chapters": []
  }
]"""
        result = self.parser.parse(
            json_str,
            "Array best match test",
            expected_keys=["totalWords", "globalGuidelines", "chapters"],
        )
        # The second element should be extracted since it matched 3 keys
        self.assertEqual(result["totalWords"], 40000)
        self.assertEqual(len(result["globalGuidelines"]), 2)

    def test_key_alias_recovery(self):
        """Test key alias recovery."""
        json_str = """{
  "templateName": "test_template",
  "selectionReason": "This is a test"
}"""
        result = self.parser.parse(
            json_str,
            "Key alias testing",
            expected_keys=["template_name", "selection_reason"],
        )
        # should automatically map templateName -> template_name
        self.assertEqual(result["template_name"], "test_template")
        self.assertEqual(result["selection_reason"], "This is a test")

    def test_complex_real_world_case(self):
        """Test real-world complex cases (similar to actual bugs)."""
        # Simulate actual errors: missing comma, markdown package, and thinking content
        json_str = """<thinking>I need to construct a space plan</thinking>
```json
{"totalWords": 40000,
  "tolerance": 2000,
  "globalGuidelines": [
    "重点突出技术红利分配失衡、人才流失与职业认同危机等结构性矛盾"
    "详略策略：技术创新与传统技艺的碰撞"
    "案例导向：优先引用真实数据和调研"
  ],
  "chapters": [
    {
      "chapterId": "ch1",
      "targetWords": 5000
    }
  ]
}
```"""
        result = self.parser.parse(json_str, "Complex real case testing")
        self.assertEqual(result["totalWords"], 40000)
        self.assertEqual(result["tolerance"], 2000)
        self.assertEqual(len(result["globalGuidelines"]), 3)
        self.assertEqual(len(result["chapters"]), 1)

    def test_expected_keys_validation(self):
        """Tests validation of expected keys."""
        json_str = '{"name": "test"}'
        # Should not fail for missing keys, just warn
        result = self.parser.parse(
            json_str, "Key verification test", expected_keys=["name", "value"]
        )
        self.assertIn("name", result)

    def test_wrapper_key_extraction(self):
        """Test extracting data from package keys."""
        json_str = """{
  "wrapper": {
    "name": "test",
    "value": 123
  }
}"""
        result = self.parser.parse(
            json_str, "Wrap key test", extract_wrapper_key="wrapper"
        )
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_empty_input(self):
        """Test empty input."""
        with self.assertRaises(JSONParseError):
            self.parser.parse("", "Empty input test")

    def test_invalid_json_after_all_repairs(self):
        """Test situations that all repair strategies fail to handle."""
        # This is a severely corrupted JSON that cannot be repaired
        json_str = "{Content not in JSON format at all###"
        with self.assertRaises(JSONParseError):
            self.parser.parse(json_str, "Unable to fix test")


def run_manual_test():
    """Run the test manually, printing details."""
    print("=" * 60)
    print("Start testing RobustJSONParser")
    print("=" * 60)

    parser = RobustJSONParser(enable_json_repair=False, enable_llm_repair=False)

    # Test actual error cases
    test_case = """```json
{
  "totalWords": 40000,
  "tolerance": 2000,
  "globalGuidelines": [
    "重点突出技术红利分配失衡、人才流失与职业认同危机等结构性矛盾"
    "详略策略：技术创新与传统技艺的碰撞"
  ],
  "chapters": []
}
```"""

    print("\nTest case:")
    print(test_case)
    print("\n" + "=" * 60)

    try:
        result = parser.parse(test_case, "Manual testing")
        print("\n✓ Parsing successful!")
        print("\nAnalysis results:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"\n✗ Parse failed: {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Run manual tests
    run_manual_test()

    # Run unit tests
    print("\n\nRun unit tests...")
    unittest.main(verbosity=2)
