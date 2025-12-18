"""Form validation and repair tools.

Provides validation and repair capabilities for IR table data:
1. Verify whether the table data format meets the IR schema requirements
2. Detect nested cells structure problems
3. Verify the basic format of rows/cells
4. Check data integrity
5. Local rules fix common problems"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class TableValidationResult:
    """Table validation results"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    nested_cells_detected: bool = False
    empty_cells_count: int = 0
    total_cells_count: int = 0

    def has_critical_errors(self) -> bool:
        """Are there any serious errors (which will cause rendering failure)"""
        return not self.is_valid and len(self.errors) > 0


@dataclass
class TableRepairResult:
    """Table repair results"""
    success: bool
    repaired_block: Optional[Dict[str, Any]]
    changes: List[str]

    def has_changes(self) -> bool:
        """Is there any modification?"""
        return len(self.changes) > 0


class TableValidator:
    """Table Validator - Verifies that IR table data is formatted correctly.

    Validation rules:
    1. Basic structure verification: type, rows fields
    2. Row structure verification: each row must have a cells array
    3. Cell structure verification: each cell must have a blocks array
    4. Nested cells detection: Detect wrong nested cells structure
    5. Data integrity verification: Check for empty cells and missing data"""

    def __init__(self):
        """Initialize validator"""
        pass

    def validate(self, table_block: Dict[str, Any]) -> TableValidationResult:
        """Validate table format.

        Args:
            table_block: table type block, including type, rows and other fields

        Returns:
            TableValidationResult: validation result"""
        errors: List[str] = []
        warnings: List[str] = []
        nested_cells_detected = False
        empty_cells_count = 0
        total_cells_count = 0

        # 1. Basic structure verification
        if not isinstance(table_block, dict):
            errors.append("table_block must be of dictionary type")
            return TableValidationResult(
                False, errors, warnings, nested_cells_detected,
                empty_cells_count, total_cells_count
            )

        # 2. Check type
        block_type = table_block.get('type')
        if block_type != 'table':
            errors.append(f"block type should be 'table', actually is '{block_type}'")

        # 3. Verify the rows field
        rows = table_block.get('rows')
        if rows is None:
            errors.append("Missing rows field")
            return TableValidationResult(
                False, errors, warnings, nested_cells_detected,
                empty_cells_count, total_cells_count
            )

        if not isinstance(rows, list):
            errors.append("rows must be of array type")
            return TableValidationResult(
                False, errors, warnings, nested_cells_detected,
                empty_cells_count, total_cells_count
            )

        if len(rows) == 0:
            warnings.append("The rows array is empty and the table may not display properly.")

        # 4. Verify each row
        for row_idx, row in enumerate(rows):
            row_result = self._validate_row(row, row_idx)
            errors.extend(row_result['errors'])
            warnings.extend(row_result['warnings'])
            if row_result['nested_cells_detected']:
                nested_cells_detected = True
            empty_cells_count += row_result['empty_cells_count']
            total_cells_count += row_result['total_cells_count']

        # 5. Check column number consistency
        column_counts = []
        for row in rows:
            if isinstance(row, dict):
                cells = row.get('cells', [])
                if isinstance(cells, list):
                    col_count = 0
                    for cell in cells:
                        if isinstance(cell, dict):
                            col_count += int(cell.get('colspan', 1))
                        else:
                            col_count += 1
                    column_counts.append(col_count)

        if column_counts and len(set(column_counts)) > 1:
            warnings.append(
                f"The number of rows and columns is inconsistent: {column_counts}, which may cause rendering problems"
            )

        # 6. Empty cell warning
        if total_cells_count > 0 and empty_cells_count > total_cells_count * 0.5:
            warnings.append(
                f"More than 50% of cells are empty ({empty_cells_count}/{total_cells_count}),"
                "Table may be missing data"
            )

        is_valid = len(errors) == 0
        return TableValidationResult(
            is_valid, errors, warnings, nested_cells_detected,
            empty_cells_count, total_cells_count
        )

    def _validate_row(self, row: Any, row_idx: int) -> Dict[str, Any]:
        """Verify single line"""
        result = {
            'errors': [],
            'warnings': [],
            'nested_cells_detected': False,
            'empty_cells_count': 0,
            'total_cells_count': 0,
        }

        if not isinstance(row, dict):
            result['errors'].append(f"rows[{row_idx}] must be of type object")
            return result

        cells = row.get('cells')
        if cells is None:
            result['errors'].append(f"rows[{row_idx}] is missing cells field")
            return result

        if not isinstance(cells, list):
            result['errors'].append(f"rows[{row_idx}].cells must be an array type")
            return result

        if len(cells) == 0:
            result['warnings'].append(f"rows[{row_idx}].cells array is empty")

        # Validate each cell
        for cell_idx, cell in enumerate(cells):
            cell_result = self._validate_cell(cell, row_idx, cell_idx)
            result['errors'].extend(cell_result['errors'])
            result['warnings'].extend(cell_result['warnings'])
            if cell_result['nested_cells_detected']:
                result['nested_cells_detected'] = True
            if cell_result['is_empty']:
                result['empty_cells_count'] += 1
            result['total_cells_count'] += 1

        return result

    def _validate_cell(self, cell: Any, row_idx: int, cell_idx: int) -> Dict[str, Any]:
        """Validate a single cell"""
        result = {
            'errors': [],
            'warnings': [],
            'nested_cells_detected': False,
            'is_empty': False,
        }

        if not isinstance(cell, dict):
            result['errors'].append(
                f"rows[{row_idx}].cells[{cell_idx}] must be of object type"
            )
            return result

        # Detect nested cells structures (this is a common LLM error)
        if 'cells' in cell and 'blocks' not in cell:
            result['nested_cells_detected'] = True
            result['errors'].append(
                f"rows[{row_idx}].cells[{cell_idx}] Detected wrong nested cells structure,"
                "It should be blocks instead of cells"
            )
            return result

        # Validate blocks field
        blocks = cell.get('blocks')
        if blocks is None:
            result['errors'].append(
                f"rows[{row_idx}].cells[{cell_idx}] is missing blocks field"
            )
            return result

        if not isinstance(blocks, list):
            result['errors'].append(
                f"rows[{row_idx}].cells[{cell_idx}].blocks must be an array type"
            )
            return result

        # Check if it is empty
        if len(blocks) == 0:
            result['is_empty'] = True
        else:
            # Check if blocks content is valid
            has_content = False
            for block in blocks:
                if isinstance(block, dict):
                    # Check the inlines of paragraph
                    if block.get('type') == 'paragraph':
                        inlines = block.get('inlines', [])
                        for inline in inlines:
                            if isinstance(inline, dict):
                                text = inline.get('text', '')
                                if text and text.strip():
                                    has_content = True
                                    break
                    # Check for other types of text/content
                    elif block.get('text') or block.get('content'):
                        has_content = True
                        break
                if has_content:
                    break

            if not has_content:
                result['is_empty'] = True

        # Verify colspan/rowspan
        colspan = cell.get('colspan')
        if colspan is not None:
            if not isinstance(colspan, int) or colspan < 1:
                result['warnings'].append(
                    f"rows[{row_idx}].cells[{cell_idx}].colspan Invalid value: {colspan}"
                )

        rowspan = cell.get('rowspan')
        if rowspan is not None:
            if not isinstance(rowspan, int) or rowspan < 1:
                result['warnings'].append(
                    f"rows[{row_idx}].cells[{cell_idx}].rowspan Invalid value: {rowspan}"
                )

        return result

    def can_render(self, table_block: Dict[str, Any]) -> bool:
        """Determine whether the table can be rendered normally (quick check).

        Args:
            table_block: block of table type

        Returns:
            bool: whether it can be rendered normally"""
        result = self.validate(table_block)
        return result.is_valid

    def has_nested_cells(self, table_block: Dict[str, Any]) -> bool:
        """Detects whether the table contains nested cells structures.

        Args:
            table_block: block of table type

        Returns:
            bool: whether to contain nested cells"""
        result = self.validate(table_block)
        return result.nested_cells_detected


class TableRepairer:
    """Table Repairer - Attempts to repair table data.

    Repair strategy:
    1. Flatten the nested cells structure
    2. Supplement the missing blocks field
    3. Normalize cell structure
    4. Verify the repair results"""

    def __init__(self, validator: Optional[TableValidator] = None):
        """Initialize the fixer.

        Args:
            validator: form validator instance"""
        self.validator = validator or TableValidator()

    def repair(
        self,
        table_block: Dict[str, Any],
        validation_result: Optional[TableValidationResult] = None
    ) -> TableRepairResult:
        """Try to fix the table data.

        Args:
            table_block: block of table type
            validation_result: validation result (optional, if not, it will be verified first)

        Returns:
            TableRepairResult: Repair result"""
        # 1. If there is no verification result, verify first
        if validation_result is None:
            validation_result = self.validator.validate(table_block)

        # 2. If it is already valid, return the original data
        if validation_result.is_valid and not validation_result.nested_cells_detected:
            return TableRepairResult(True, table_block, [])

        # 3. Try to repair
        repaired = copy.deepcopy(table_block)
        changes: List[str] = []

        # Ensure basic structure
        if 'type' not in repaired:
            repaired['type'] = 'table'
            changes.append("Add missing type field")

        if 'rows' not in repaired or not isinstance(repaired.get('rows'), list):
            repaired['rows'] = []
            changes.append("Add missing rows field")

        # fix every line
        repaired_rows: List[Dict[str, Any]] = []
        for row_idx, row in enumerate(repaired.get('rows', [])):
            repaired_row, row_changes = self._repair_row(row, row_idx)
            repaired_rows.append(repaired_row)
            changes.extend(row_changes)

        repaired['rows'] = repaired_rows

        # 4. Verify the repair results
        repaired_validation = self.validator.validate(repaired)
        success = repaired_validation.is_valid

        if not success:
            logger.warning(
                f"There are still problems after the table is repaired: {repaired_validation.errors}"
            )

        return TableRepairResult(success, repaired, changes)

    def _repair_row(
        self, row: Any, row_idx: int
    ) -> Tuple[Dict[str, Any], List[str]]:
        """fix single line"""
        changes: List[str] = []

        if not isinstance(row, dict):
            return {'cells': [self._default_cell()]}, [
                f"rows[{row_idx}] type error, rebuilt"
            ]

        repaired_row = dict(row)

        # Make sure there is a cells field
        if 'cells' not in repaired_row or not isinstance(repaired_row.get('cells'), list):
            repaired_row['cells'] = [self._default_cell()]
            changes.append(f"rows[{row_idx}] adds missing cells field")
            return repaired_row, changes

        # Repair every cell
        repaired_cells: List[Dict[str, Any]] = []
        for cell_idx, cell in enumerate(repaired_row.get('cells', [])):
            if isinstance(cell, dict) and 'cells' in cell and 'blocks' not in cell:
                # Flatten nested cells
                flattened = self._flatten_nested_cells(cell)
                repaired_cells.extend(flattened)
                changes.append(
                    f"rows[{row_idx}].cells[{cell_idx}] flatten nested cells structure"
                )
            else:
                repaired_cell, cell_changes = self._repair_cell(cell, row_idx, cell_idx)
                repaired_cells.append(repaired_cell)
                changes.extend(cell_changes)

        repaired_row['cells'] = repaired_cells
        return repaired_row, changes

    def _repair_cell(
        self, cell: Any, row_idx: int, cell_idx: int
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Repair a single cell"""
        changes: List[str] = []

        if not isinstance(cell, dict):
            if isinstance(cell, (str, int, float)):
                return {
                    'blocks': [self._text_to_paragraph(str(cell))]
                }, [f"rows[{row_idx}].cells[{cell_idx}] converted to standard format"]
            return self._default_cell(), [
                f"rows[{row_idx}].cells[{cell_idx}] type error, has been rebuilt"
            ]

        repaired_cell = dict(cell)

        # Make sure there is a blocks field
        if 'blocks' not in repaired_cell:
            # Try to extract content from other fields
            text = ''
            for key in ('text', 'content', 'value'):
                if key in repaired_cell and repaired_cell[key]:
                    text = str(repaired_cell[key])
                    break

            repaired_cell['blocks'] = [self._text_to_paragraph(text or '')]
            changes.append(
                f"rows[{row_idx}].cells[{cell_idx}] adds missing blocks field"
            )
        elif not isinstance(repaired_cell['blocks'], list):
            repaired_cell['blocks'] = [self._text_to_paragraph('')]
            changes.append(
                f"rows[{row_idx}].cells[{cell_idx}].blocks type error, has been rebuilt"
            )
        elif len(repaired_cell['blocks']) == 0:
            repaired_cell['blocks'] = [self._text_to_paragraph('')]
            changes.append(
                f"rows[{row_idx}].cells[{cell_idx}].blocks is empty, add default content"
            )

        return repaired_cell, changes

    def _flatten_nested_cells(self, cell: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten nested cells structure"""
        nested_cells = cell.get('cells', [])
        if not isinstance(nested_cells, list):
            return [self._default_cell()]

        result: List[Dict[str, Any]] = []
        for nested in nested_cells:
            if isinstance(nested, dict):
                if 'blocks' in nested and 'cells' not in nested:
                    # normal cell
                    result.append(nested)
                elif 'cells' in nested and 'blocks' not in nested:
                    # Continue recursive flattening
                    result.extend(self._flatten_nested_cells(nested))
                else:
                    # try to fix
                    repaired, _ = self._repair_cell(nested, 0, 0)
                    result.append(repaired)
            elif isinstance(nested, (str, int, float)):
                result.append({
                    'blocks': [self._text_to_paragraph(str(nested))]
                })

        return result if result else [self._default_cell()]

    def _default_cell(self) -> Dict[str, Any]:
        """Create default cells"""
        return {
            'blocks': [self._text_to_paragraph('')]
        }

    def _text_to_paragraph(self, text: str) -> Dict[str, Any]:
        """Convert text to paragraph block"""
        return {
            'type': 'paragraph',
            'inlines': [{'text': text, 'marks': []}]
        }


def create_table_validator() -> TableValidator:
    """Create a form validator instance"""
    return TableValidator()


def create_table_repairer(
    validator: Optional[TableValidator] = None
) -> TableRepairer:
    """Create a table fixer instance"""
    return TableRepairer(validator)


__all__ = [
    'TableValidator',
    'TableRepairer',
    'TableValidationResult',
    'TableRepairResult',
    'create_table_validator',
    'create_table_repairer',
]
