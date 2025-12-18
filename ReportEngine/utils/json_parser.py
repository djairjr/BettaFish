"""Unified JSON parsing and repair tool.

Provides robust JSON parsing capabilities, supporting:
1. Automatically clean markdown code block marks and thinking content
2. Local grammar fixes (bracket balancing, comma completion, control character escaping, etc.)
3. Use json_repair library for advanced repair
4. LLM-assisted repair (optional)
5. Detailed error logs and debugging information"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Callable
from loguru import logger

try:
    from json_repair import repair_json as _json_repair_fn
except ImportError:
    _json_repair_fn = None


class JSONParseError(ValueError):
    """Exception thrown when JSON parsing fails, with original text attached for easy troubleshooting."""

    def __init__(self, message: str, raw_text: Optional[str] = None):
        """Construct an exception and attach raw output for easy location in the log.

        Args:
            message: Human-readable error description.
            raw_text: The complete LLM output that triggered the exception."""
        super().__init__(message)
        self.raw_text = raw_text


class RobustJSONParser:
    """Robust JSON parser.

    Integrate multiple repair strategies to ensure that the content returned by LLM can be correctly parsed:
    - Clean up markdown packages, thinking content and other additional information
    - Fixed common grammatical errors (missing commas, unbalanced brackets, etc.)
    - Escape unescaped control characters
    - Use third-party libraries for advanced repairs
    - Optional LLM assisted repair"""

    # Common LLM thinking content patterns
    _THINKING_PATTERNS = [
        r"^\s*<thinking>.*?</thinking>\s*",
        r"^\s*<thought>.*?</thought>\s*",
        r"^\s*Let me think.*?(?=\{|\[|$)",
        r"^\s*First.*?(?=\{|\[|$)",
        r"^\s*Analysis.*?(?=\{|\[|$)",
        r"^\s*according to.*?(?=\{|\[|$)",
    ]

    # Colon equal sign pattern (common LLM errors)
    _COLON_EQUALS_PATTERN = re.compile(r'(":\s*)=')

    def __init__(
        self,
        llm_repair_fn: Optional[Callable[[str, str], Optional[str]]] = None,
        enable_json_repair: bool = True,
        enable_llm_repair: bool = False,
        max_repair_attempts: int = 3,
    ):
        """
        初始化JSON解析器。

        Args:
            llm_repair_fn: 可选的LLM修复函数，接收(原始JSON, 错误信息)返回修复后的JSON
            enable_json_repair: 是否启用json_repair库
            enable_llm_repair: 是否启用LLM辅助修复
            max_repair_attempts: 最大修复尝试次数
        """
        self.llm_repair_fn = llm_repair_fn
        self.enable_json_repair = enable_json_repair and _json_repair_fn is not None
        self.enable_llm_repair = enable_llm_repair
        self.max_repair_attempts = max_repair_attempts

    def parse(
        self,
        raw_text: str,
        context_name: str = "JSON",
        expected_keys: Optional[List[str]] = None,
        extract_wrapper_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        解析LLM返回的JSON文本。

        参数:
            raw_text: LLM原始输出（可能包含```包裹、思考内容等）
            context_name: 上下文名称，用于错误信息
            expected_keys: 期望的键列表，用于验证
            extract_wrapper_key: 如果JSON被包裹在某个键中，指定该键名进行提取

        返回:
            dict: 解析后的JSON对象

        异常:
            JSONParseError: 多种修复策略仍无法解析合法JSON
        """
        if not raw_text or not raw_text.strip():
            raise JSONParseError(f"{context_name}返回空内容")

        # Original text for subsequent logs
        original_text = raw_text

        # Step 1: Construct a candidate set, including different cleaning strategies
        candidates = self._build_candidate_payloads(raw_text, context_name)

        # Step 2: Try to parse all candidates
        last_error: Optional[json.JSONDecodeError] = None
        for i, candidate in enumerate(candidates):
            try:
                data = json.loads(candidate)
                logger.debug(f"ates):
            try:
                data = json.loads(candidate)
                logger.debug(f"{context_name} JSON解析成功（候选{i + 1}/{len(candidates)}）")
                return self._extract_and_validate(
                    data, expected_keys, extract_wrapper_key, context_name
                )
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.debug(f"{context_name} 候选{i + 1}解析失败: {exc}")

        cleaned = candidates[0] if candidates else original_text

        # Step 3: Use json_repair library
        if self.enable_json_repair:
            repaired = self._attempt_json_repair(cleaned, context_name)
            if repaired:
                try:
                    data = json.loads(repaired)
                    logger.info(f"gger.info(f"{context_name} JSON通过json_repair库修复成功")
                    return self._extract_and_validate(
                        data, expected_keys, extract_wrapper_key, context_name
                    )
                except json.JSONDecodeError as exc:
                    last_error = exc
                    logger.debug(f"{context_name} json_repair修复后仍无法解析: {exc}")

        # Step 4: Repair using LLM (if enabled)
        if self.enable_llm_repair and self.llm_repair_fn:
            llm_repaired = self._attempt_llm_repair(cleaned, str(last_error), context_name)
            if llm_repaired:
                try:
                    data = json.loads(llm_repaired)
                    logger.info(f"     logger.info(f"{context_name} JSON通过LLM修复成功")
                    return self._extract_and_validate(
                        data, expected_keys, extract_wrapper_key, context_name
                    )
                except json.JSONDecodeError as exc:
                    last_error = exc
                    logger.warning(f"{context_name} LLM修复后仍无法解析: {exc}")

        # All strategies failed
        error_msg = f"rror_msg = f"{context_name} JSON解析失败: {last_error}"
        logger.error(error_msg)
        logger.debug(f"原始文本前500字符: {original_text[:500]}")
        raise JSONParseError(error_msg, raw_text=original_text) from last_error

    def _build_candidate_payloads(self, raw_text: str, context_name: str) -> List[str]:
        """
        针对原始文本构造多个候选JSON字符串，覆盖不同的清理策略。

        返回:
            List[str]: 候选JSON文本列表
        """cleaned = self._clean_response(raw_text)
        candidates = [cleaned]

        local_repaired = self._apply_local_repairs(cleaned)
        if local_repaired != cleaned:
            candidates.append(local_repaired)

        #Forcibly flatten content containing a three-layer list structure once
        flattened = self._flatten_nested_arrays(local_repaired)
        if flattened not in candidates:
            candidates.append(flattened)

        return candidates

    def _clean_response(self, raw: str) -> str:"def _clean_response(self, raw: str) -> str:
        """
        清理LLM响应，去除markdown标记和思考内容。

        参数:
            raw: LLM原始输出

        返回:
            str: 清理后的文本
        """cleaned = raw.strip()

        # Remove thinking content (multi-language support)
        for pattern in self._THINKING_PATTERNS:
            cleaned = re.sub(pattern,"cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        # Prioritize extracting the ```json``` package content at any location
        fenced_match = re.search(r" location
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fenced_match:
            cleaned = fenced_match.group(1).strip()
        else:
            # If the complete code block is not found, try removing the suffix and suffix again
            if cleaned.startswith("e suffix and suffix again
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]

            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            cleaned = cleaned.strip()

        # Try to extract the first complete JSON object or array
        cleaned = self._extract_first_json_structure(cleaned)

        return cleaned

    def _extract_first_json_structure(self, text: str) -> str:"(self, text: str) -> str:
        """
        从文本中提取第一个完整的JSON对象或数组。

        这对于处理LLM在JSON前后添加说明文字的情况很有用。

        参数:
            text: 可能包含JSON的文本

        返回:
            str: 提取的JSON文本，如果找不到则返回原文本
        """# Find the first { or [
        start_brace = text.find("ext.find("{")
        start_bracket = text.find("[")

        if start_brace == -1 and start_bracket == -1:
            return text

        # Determine starting position
        if start_brace == -1:
            start = start_bracket
            opener ="           opener = "["
            closer = "]"
        elif start_bracket == -1:
            start = start_brace
            opener = "{"
            closer = "}"
        else:
            start = min(start_brace, start_bracket)
            opener = text[start]
            closer = "}" if opener == "{" else "]"# Find the corresponding end position
        depth = 0
        in_string = False
        escaped=False

        for i in range(start, len(text)):
            ch = text[i]

            if escaped:
                escaped=False
                continue

            if ch =="ue

            if ch == "\\":
                escaped = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        # If the complete structure is not found, return from the starting position to the end
        return text[start:] if start < len(text) else text

    def _apply_local_repairs(self, text: str) -> str:
        """Apply local remediation strategies.

        Parameters:
            text: original JSON text

        Return:
            str: repaired text"""
        repaired = text
        mutated = False

        # Fix ":=" error
        new_text = self._COLON_EQUALS_PATTERN.sub(r"\1", repaired)
        if new_text != repaired:
            logger.warning("The \":=\" character was detected and the extra '=' sign was automatically removed.")
            repaired = new_text
            mutated = True

        # Escape control characters
        repaired, escaped = self._escape_control_characters(repaired)
        if escaped:
            logger.warning("Unescaped control character detected, automatically converted to escape sequence")
            mutated = True

        # Fix missing commas
        repaired, commas_fixed = self._fix_missing_commas(repaired)
        if commas_fixed:
            logger.warning("Missing commas between objects/arrays detected and automatically completed")
            mutated = True

        # Merge redundant square brackets (LLM often writes two-dimensional list levels into three levels)
        repaired, brackets_collapsed = self._collapse_redundant_brackets(repaired)
        if brackets_collapsed:
            logger.warning("Continuous nesting of square brackets detected, attempted collapse into 2D structure")
            mutated = True

        # balanced brackets
        repaired, balanced = self._balance_brackets(repaired)
        if balanced:
            logger.warning("Unbalanced brackets were detected and abnormal brackets were automatically completed/removed.")
            mutated = True

        # Remove trailing commas
        repaired, trailing_removed = self._remove_trailing_commas(repaired)
        if trailing_removed:
            logger.warning("Trailing comma detected, automatically removed")
            mutated = True

        return repaired if mutated else text

    def _escape_control_characters(self, text: str) -> Tuple[str, bool]:
        """Replace naked newlines/tabs/control characters in string literals with JSON-legal escape sequences.

        Parameters:
            text: original JSON text

        Return:
            Tuple[str, bool]: (repaired text, whether there are any modifications)"""
        if not text:
            return text, False

        result: List[str] = []
        in_string = False
        escaped = False
        mutated = False
        control_map = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if in_string and ch in control_map:
                result.append(control_map[ch])
                mutated = True
                continue

            if in_string and ord(ch) < 0x20:
                result.append(f"\\u{ord(ch):04x}")
                mutated = True
                continue

            result.append(ch)

        return "".join(result), mutated

    def _fix_missing_commas(self, text: str) -> Tuple[str, bool]:
        """
        在对象/数组元素之间自动补逗号。

        参数:
            text: 原始JSON文本

        返回:
            Tuple[str, bool]: (修复后的文本, 是否有修改)
        """
        if not text:
            return text, False

        chars: List[str] = []
        mutated = False
        in_string = False
        escaped = False
        length = len(text)
        i = 0

        while i < length:
            ch = text[i]
            chars.append(ch)

            if escaped:
                escaped = False
                i += 1
                continue

            if ch == "\\":
                escaped = True
                i += 1
                continue

            if ch == '"':
                # If we are exiting a string, check if a comma is needed after
                if in_string:
                    # Find next non-whitespace character
                    j = i + 1
                    while j < length and text[j] in " \t\r\n":
                        j += 1
                    # A comma may be required if the next character is " { [ or a numbercomma may be required
                    if j < length:
                        next_ch = text[j]
                        if next_ch in"\"[{" or next_ch.isdigit():
                            # Check if already in object or array
                            # By checking if it is preceded by an unclosed { or [
                            has_opener = False
                            for k in range(len(chars) - 1, -1, -1):
                                if chars[k] in "{[":
                                    has_opener = True
                                    break
                                elif chars[k] in "]}":
                                    break

                            if has_opener:
                                chars.append(",")
                                mutated = True

                in_string = not in_string
                i += 1
                continue

            # Check if comma is required after } or ]
            if not in_string and ch in "}]":
                j = i + 1
                # Skip whitespace
                while j < length and text[j] in " \t\r\n":
                    j += 1
                # If the next non-whitespace character is { [ " or a number, add a commas, add a comma
                if j < length:
                    next_ch = text[j]
                    if next_ch in"{[\"" or next_ch.isdigit():
                        chars.append(",")
                        mutated = True

            i += 1

        return "".join(chars), mutated

    def _collapse_redundant_brackets(self, text: str) -> Tuple[str, bool]:
        """Fold three or more levels of arrays (such as ]]], [[ / [[[) generated by LLM to avoid writing extra dimensions in tables/lists.

        Return:
            Tuple[str, bool]: (repaired text, whether there are any modifications)"""
        if not text:
            return text, False

        mutated = False

        patterns = [
            # Typical errors: "]]], [[{...}" -> "]], [{...}"
            (re.compile(r"\]\s*\]\s*\]\s*,\s*\[\s*\["), "]],["),
            # Extreme case: three consecutive levels starting with "[[[" -> "[["
            (re.compile(r"\[\s*\[\s*\["), "[["),
            # Extreme case: ending "]]]" -> "]]"
            (re.compile(r"\]\s*\]\s*\]"), "]]"),
        ]

        repaired = text
        for pattern, replacement in patterns:
            new_text, count = pattern.subn(replacement, repaired)
            if count > 0:
                mutated = True
                repaired = new_text

        return repaired, mutated

    def _flatten_nested_arrays(self, text: str) -> str:
        """Collapse an obviously redundant one-level list, such as [[[x]]] -> [[x]]."""
        if not text:
            return text
        text = re.sub(r"\]\s*\]\s*\]", "]]", text)
        text = re.sub(r"\[\s*\[\s*\[", "[[", text)
        return text

    def _balance_brackets(self, text: str) -> Tuple[str, bool]:
        """Try to fix unbalanced structures caused by LLM writing more/less parentheses.

        Parameters:
            text: original JSON text

        Return:
            Tuple[str, bool]: (repaired text, whether there are any modifications)"""
        if not text:
            return text, False

        result: List[str] = []
        stack: List[str] = []
        mutated = False
        in_string = False
        escaped = False

        opener_map = {"{": "}", "[": "]"}

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if in_string:
                result.append(ch)
                continue

            if ch in "{[":
                stack.append(ch)
                result.append(ch)
                continue

            if ch in "}]":
                if stack and (
                    (ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")
                ):
                    stack.pop()
                    result.append(ch)
                else:
                    # Unmatched closing brackets, ignored
                    mutated=True
                continue

            result.append(ch)

        # Complete unclosed brackets
        while stack:
            opener = stack.pop()
            result.append(opener_map[opener])
            mutated=True

        return")
            mutated = True

        return "".join(result), mutated

    def _remove_trailing_commas(self, text: str) -> Tuple[str, bool]:
        """
        移除JSON对象和数组中的尾随逗号。

        参数:
            text: 原始JSON文本

        返回:
            Tuple[str, bool]: (修复后的文本, 是否有修改)
        """if not text:
            return text, False

        # Remove trailing commas using regular expressions
        # Match , followed by whitespace and } or ]
        pattern = r" followed by whitespace and } or ]
        pattern = r",(\s*[}\]])"
        new_text = re.sub(pattern, r"\1", text)

        return new_text, new_text != text

    def _attempt_json_repair(self, text: str, context_name: str) -> Optional[str]:
        """
        使用json_repair库进行高级修复。

        参数:
            text: 原始JSON文本
            context_name: 上下文名称

        返回:
            Optional[str]: 修复后的JSON文本，失败返回None
        """
        if not _json_repair_fn:
            return None

        try:
            fixed = _json_repair_fn(text)
            if fixed and fixed != text:
                logger.info(f"{context_name} 使用json_repair库自动修复JSON")
                return fixed
        except Exception as exc:
            logger.debug(f"{context_name} json_repair修复失败: {exc}")

        return None

    def _attempt_llm_repair(
        self, text: str, error_msg: str, context_name: str
    ) -> Optional[str]:
        """
        使用LLM进行JSON修复。

        参数:
            text: 原始JSON文本
            error_msg: 解析错误信息
            context_name: 上下文名称

        返回:
            Optional[str]: 修复后的JSON文本，失败返回None
        """
        if not self.llm_repair_fn:
            return None

        try:
            logger.info(f"{context_name} 尝试使用LLM修复JSON")
            repaired = self.llm_repair_fn(text, error_msg)
            if repaired and repaired != text:
                return repaired
        except Exception as exc:
            logger.warning(f"{context_name} LLM修复失败: {exc}")

        return None

    def _extract_and_validate(
        self,
        data: Any,
        expected_keys: Optional[List[str]],
        extract_wrapper_key: Optional[str],
        context_name: str,
    ) -> Dict[str, Any]:
        """
        提取并验证JSON数据。

        参数:
            data: 解析后的数据
            expected_keys: 期望的键列表
            extract_wrapper_key: 包裹键名
            context_name: 上下文名称

        返回:
            Dict[str, Any]: 提取并验证后的数据

        异常:
            JSONParseError: 如果数据格式不符合预期
        """# Extract package data
        if extract_wrapper_key and isinstance(data, dict):
            if extract_wrapper_key in data:
                data = data[extract_wrapper_key]
            else:
                logger.warning(
                    f"           f"{context_name} 未找到包裹键'{extract_wrapper_key}'，使用原始数据")

        # Verify data type
        if not isinstance(data, dict):
            if isinstance(data, list):
                if len(data) > 0:
                    # Try to find the element that best matches the expectation
                    best_match = None
                    max_match_count = 0

                    for item in data:
                        if isinstance(item, dict):
                            if expected_keys:
                                # Count the number of matching keys
                                match_count = sum(1 for key in expected_keys if key in item)
                                if match_count > max_match_count:
                                    max_match_count = match_count
                                    best_match = item
                            elif best_match is None:
                                best_match = item

                    if best_match:
                        logger.warning(
                            f"f best_match:
                        logger.warning(
                            f"{context_name} 返回数组，自动提取最佳匹配元素（匹配{max_match_count}/{len(expected_keys or [])}个键）"
                        )
                        data = best_match
                    else:
                        raise JSONParseError(
                            f"{context_name} 返回的数组中没有有效的对象"
                        )
                else:
                    raise JSONParseError(f"{context_name} 返回空数组")
            else:
                raise JSONParseError(
                    f"{context_name} 返回的不是JSON对象: {type(data).__name__}")

        # Verify required keys
        if expected_keys:
            missing_keys = [key for key in expected_keys if key not in data]
            if missing_keys:
                logger.warning(
                    f"            f"{context_name} 缺少预期的键: {', '.join(missing_keys)}")
                # Attempt to fix common key name variations
                data = self._try_recover_missing_keys(data, missing_keys, context_name)

        return data

    def _try_recover_missing_keys(
        self, data: Dict[str, Any], missing_keys: List[str], context_name: str
    ) -> Dict[str, Any]:" Dict[str, Any]:
        """
        尝试从数据中恢复缺失的键，通过查找相似的键名。

        参数:
            data: 原始数据
            missing_keys: 缺失的键列表
            context_name: 上下文名称

        返回:
            Dict[str, Any]: 修复后的数据
        """# Common key name mapping
        key_aliases = {"= {
            "template_name": ["templateName", "name", "template"],
            "selection_reason": ["selectionReason", "reason", "explanation"],
            "title": ["reportTitle", "documentTitle"],
            "chapters": ["chapterList", "chapterPlan", "sections"],
            "totalWords": ["total_words", "wordCount", "totalWordCount"],
        }

        for missing_key in missing_keys:
            if missing_key in key_aliases:
                for alias in key_aliases[missing_key]:
                    if alias in data:
                        logger.info(
                            f"{context_name} 找到键'{missing_key}'的别名'{alias}'，自动映射"
                        )
                        data[missing_key] = data[alias]
                        break

        return data


__all__ = ["RobustJSONParser", "JSONParseError"]
