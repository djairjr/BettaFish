"""Chart validation and repair tools.

Provides verification and repair capabilities for Chart.js chart data:
1. Verify whether the chart data format meets the requirements of Chart.js
2. Local rules fix common problems
3. LLM API assists in repairing complex problems
4. Follow"宁愿不改，也不要改错"principles

Supported chart types:
- line (line chart)
- bar (bar chart)
- pie (pie chart)
- doughnut (donut chart)
- radar
- polarArea (polar area map)
- scatter (scatter plot)"""

from __future__ import annotations

import copy
import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from loguru import logger


@dataclass
class ValidationResult:
    """Verification results"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]

    def has_critical_errors(self) -> bool:
        """Are there any serious errors (which will cause rendering failure)"""
        return not self.is_valid and len(self.errors) > 0


@dataclass
class RepairResult:
    """Repair results"""
    success: bool
    repaired_block: Optional[Dict[str, Any]]
    method: str  # 'none', 'local', 'api'
    changes: List[str]

    def has_changes(self) -> bool:
        """Is there any modification?"""
        return len(self.changes) > 0


class ChartValidator:
    """Chart Validator - Verifies whether the Chart.js chart data format is correct.

    Validation rules:
    1. Basic structure verification: widgetType, props, data fields
    2. Chart type verification: supported chart types
    3. Data format verification: labels and datasets structure
    4. Data consistency verification: labels and datasets length match
    5. Numeric type verification: the data value type is correct"""

    # Supported chart types
    SUPPORTED_CHART_TYPES = {
        'line', 'bar', 'pie', 'doughnut', 'radar', 'polarArea', 'scatter',
        'bubble', 'horizontalBar'
    }

    # Chart type that requires labels
    LABEL_REQUIRED_TYPES = {
        'line', 'bar', 'radar', 'polarArea', 'pie', 'doughnut'
    }

    # Chart types that require numeric data
    NUMERIC_DATA_TYPES = {
        'line', 'bar', 'radar', 'polarArea', 'pie', 'doughnut'
    }

    # Chart types that require special data formats
    SPECIAL_DATA_TYPES = {
        'scatter': {'x', 'y'},
        'bubble': {'x', 'y', 'r'}
    }

    def __init__(self):
        """Initialize the validator and reserve the cache structure to facilitate subsequent reuse of verification/repair results."""

    def validate(self, widget_block: Dict[str, Any]) -> ValidationResult:
        """Validate chart format.

        Args:
            widget_block: block of widget type, including widgetId/widgetType/props/data

        Returns:
            ValidationResult: Validation result"""
        errors = []
        warnings = []

        # 1. Basic structure verification
        if not isinstance(widget_block, dict):
            errors.append("widget_block must be of dictionary type")
            return ValidationResult(False, errors, warnings)

        # 2. Check widgetType
        widget_type = widget_block.get('widgetType', '')
        if not widget_type or not isinstance(widget_type, str):
            errors.append("The widgetType field is missing or incorrect type")
            return ValidationResult(False, errors, warnings)

        # Check if it is chart.js type
        if not widget_type.startswith('chart.js'):
            # Not a chart type, skip validation
            return ValidationResult(True, errors, warnings)

        # 3. Extract chart type
        chart_type = self._extract_chart_type(widget_block)
        if not chart_type:
            errors.append("Unable to determine chart type")
            return ValidationResult(False, errors, warnings)

        # 4. Check whether the chart type is supported
        if chart_type not in self.SUPPORTED_CHART_TYPES:
            warnings.append(f"Chart type '{chart_type}' may not be supported, downgrade rendering will be attempted")

        # 5. Verify data structure
        data = widget_block.get('data')
        if not isinstance(data, dict):
            errors.append("The data field must be of dictionary type")
            return ValidationResult(False, errors, warnings)

        # Check if data points of the form {x, y} are used (usually used for timelines/scatter points)
        def contains_object_points(ds_list: List[Any] | None) -> bool:
            """Check whether the data set contains object points represented by x/y keys, used to switch the verification branch"""
            if not isinstance(ds_list, list):
                return False
            for point in ds_list:
                if isinstance(point, dict) and any(key in point for key in ('x', 'y', 't')):
                    return True
            return False

        datasets_for_detection = data.get('datasets') or []
        uses_object_points = any(
            isinstance(ds, dict) and contains_object_points(ds.get('data'))
            for ds in datasets_for_detection
        )

        # 6. Validate data based on chart type
        if chart_type in self.SPECIAL_DATA_TYPES:
            # Special data formats (scatter, bubble)
            self._validate_special_data(data, chart_type, errors, warnings)
        else:
            # Standard data format (labels + datasets)
            self._validate_standard_data(data, chart_type, errors, warnings, uses_object_points)

        # 7. Verify props
        props = widget_block.get('props')
        if props is not None and not isinstance(props, dict):
            warnings.append("The props field should be of dictionary type")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings)

    def _extract_chart_type(self, widget_block: Dict[str, Any]) -> Optional[str]:
        """Extract chart type.

        Priority:
        1.props.type
        2. Type in widgetType (chart.js/bar -> bar)
        3.data.type"""
        # 1. Get from props
        props = widget_block.get('props') or {}
        if isinstance(props, dict):
            chart_type = props.get('type')
            if chart_type and isinstance(chart_type, str):
                return chart_type.lower()

        # 2. Extract from widgetType
        widget_type = widget_block.get('widgetType', '')
        if '/' in widget_type:
            chart_type = widget_type.split('/')[-1]
            if chart_type:
                return chart_type.lower()

        # 3. Get from data
        data = widget_block.get('data') or {}
        if isinstance(data, dict):
            chart_type = data.get('type')
            if chart_type and isinstance(chart_type, str):
                return chart_type.lower()

        return None

    def _validate_standard_data(
        self,
        data: Dict[str, Any],
        chart_type: str,
        errors: List[str],
        warnings: List[str],
        uses_object_points: bool = False
    ):
        """Validate standard data formats (labels + datasets)"""
        labels = data.get('labels')
        datasets = data.get('datasets')

        # Verify labels
        if chart_type in self.LABEL_REQUIRED_TYPES:
            if not labels:
                if uses_object_points:
                    warnings.append(
                        f"Chart of type {chart_type} is missing labels and has been rendered based on data points (using x values)"
                    )
                else:
                    errors.append(f"Charts of type {chart_type} must contain labels field")
            elif not isinstance(labels, list):
                errors.append("labels must be of array type")
            elif len(labels) == 0:
                warnings.append("The labels array is empty and the chart may not display properly.")

        # Verify datasets
        if datasets is None:
            errors.append("Missing datasets field")
            return

        if not isinstance(datasets, list):
            errors.append("datasets must be of array type")
            return

        if len(datasets) == 0:
            errors.append("datasets array is empty")
            return

        # Verify each dataset
        for idx, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                errors.append(f"datasets[{idx}] must be of type object")
                continue

            # Verify data field
            ds_data = dataset.get('data')
            if ds_data is None:
                errors.append(f"datasets[{idx}] is missing data field")
                continue

            if not isinstance(ds_data, list):
                errors.append(f"datasets[{idx}].data must be an array type")
                continue

            if len(ds_data) == 0:
                warnings.append(f"datasets[{idx}].data array is empty")
                continue

            # If it is a data point in the form of {x, y} object, the labels length and value verification are allowed to be skipped by default.
            object_points = any(
                isinstance(value, dict) and any(key in value for key in ('x', 'y', 't'))
                for value in ds_data
            )

            # Verify data length consistency
            if labels and isinstance(labels, list) and not object_points:
                if len(ds_data) != len(labels):
                    warnings.append(
                        f"datasets[{idx}].data length ({len(ds_data)}) does not match labels length ({len(labels)})"
                    )

            # Validate numeric types
            if chart_type in self.NUMERIC_DATA_TYPES and not object_points:
                for data_idx, value in enumerate(ds_data):
                    if value is not None and not isinstance(value, (int, float)):
                        errors.append(
                            f"Value '{value}' of datasets[{idx}].data[{data_idx}] is not a valid numeric type"
                        )
                        break  # Only report the first error

    def _validate_special_data(
        self,
        data: Dict[str, Any],
        chart_type: str,
        errors: List[str],
        warnings: List[str]
    ):
        """Validate special data formats (scatter, bubble)"""
        datasets = data.get('datasets')

        if not datasets:
            errors.append("Missing datasets field")
            return

        if not isinstance(datasets, list):
            errors.append("datasets must be of array type")
            return

        if len(datasets) == 0:
            errors.append("datasets array is empty")
            return

        required_keys = self.SPECIAL_DATA_TYPES.get(chart_type, set())

        # Verify each dataset
        for idx, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                errors.append(f"datasets[{idx}] must be of type object")
                continue

            ds_data = dataset.get('data')
            if ds_data is None:
                errors.append(f"datasets[{idx}] is missing data field")
                continue

            if not isinstance(ds_data, list):
                errors.append(f"datasets[{idx}].data must be an array type")
                continue

            if len(ds_data) == 0:
                warnings.append(f"datasets[{idx}].data array is empty")
                continue

            # Verify data point format
            for data_idx, point in enumerate(ds_data):
                if not isinstance(point, dict):
                    errors.append(
                        f"datasets[{idx}].data[{data_idx}] must be of object type (containing {required_keys} fields)"
                    )
                    break

                # Check required keys
                missing_keys = required_keys - set(point.keys())
                if missing_keys:
                    errors.append(
                        f"datasets[{idx}].data[{data_idx}] is missing required fields: {missing_keys}"
                    )
                    break

                # Validate numeric types
                for key in required_keys:
                    value = point.get(key)
                    if value is not None and not isinstance(value, (int, float)):
                        errors.append(
                            f"The value '{value}' of datasets[{idx}].data[{data_idx}].{key} is not a valid numeric type"
                        )
                        break

    def can_render(self, widget_block: Dict[str, Any]) -> bool:
        """Determine whether the chart renders normally (quick check).

        Args:
            widget_block: block of widget type

        Returns:
            bool: whether it can be rendered normally"""
        result = self.validate(widget_block)
        return result.is_valid


class ChartRepairer:
    """Chart Repairer - Attempts to repair chart data.

    Repair strategy:
    1. Local rules fix: fix common problems
    2. API Repair: Use LLM to fix complex issues
    3. Verify the repair results: Make sure it can render normally after repair"""

    def __init__(
        self,
        validator: ChartValidator,
        llm_repair_fns: Optional[List[Callable]] = None
    ):
        """Initialize the fixer.

        Args:
            validator: chart validator instance
            llm_repair_fns: LLM repair function list (corresponding to 4 Engines)"""
        self.validator = validator
        self.llm_repair_fns = llm_repair_fns or []
        # Cache repair results to avoid calling LLM repeatedly for the same chart in multiple places
        self._result_cache: Dict[str, RepairResult] = {}

    def build_cache_key(self, widget_block: Dict[str, Any]) -> str:
        """Generate stable cache keys for charts to ensure that the same data will not trigger repairs repeatedly.

        - Use widgetId first;
        - Combined with the hash of the data content to avoid misuse of old results when the content of the same ID changes."""
        widget_id = ""
        if isinstance(widget_block, dict):
            widget_id = widget_block.get('widgetId') or widget_block.get('id') or ""
        try:
            serialized = json.dumps(
                widget_block,
                ensure_ascii=False,
                sort_keys=True,
                default=str
            )
        except Exception:
            serialized = repr(widget_block)
        digest = hashlib.md5(serialized.encode('utf-8', errors='ignore')).hexdigest()
        return f"{widget_id}:{digest}"

    def repair(
        self,
        widget_block: Dict[str, Any],
        validation_result: Optional[ValidationResult] = None
    ) -> RepairResult:
        """Try to fix the chart data.

        Args:
            widget_block: block of widget type
            validation_result: validation result (optional, if not, it will be verified first)

        Returns:
            RepairResult: Repair result"""
        cache_key = self.build_cache_key(widget_block)

        cached = self._result_cache.get(cache_key)
        if cached:
            # Return a deep copy of the cache to avoid external modifications affecting the cache
            return copy.deepcopy(cached)

        def _cache_and_return(res: RepairResult) -> RepairResult:
            """Write the repair result cache and return it to avoid repeated calls to downstream repair logic"""
            try:
                self._result_cache[cache_key] = copy.deepcopy(res)
            except Exception:
                self._result_cache[cache_key] = res
            return res

        # 1. If there is no verification result, verify first
        if validation_result is None:
            validation_result = self.validator.validate(widget_block)

        # Keep track of the latest verification results and data
        current_validation = validation_result
        current_block = widget_block

        # 2. Try local repair (try even if verification passes, as there may be warnings)
        logger.info(f"Try to fix the chart locally")
        local_result = self.repair_locally(widget_block, validation_result)

        # 3. Verify local repair results
        if local_result.has_changes():
            repaired_validation = self.validator.validate(local_result.repaired_block)
            if repaired_validation.is_valid:
                logger.info(f"Local repair successful: {local_result.changes}")
                return _cache_and_return(
                    RepairResult(True, local_result.repaired_block, 'local', local_result.changes)
                )
            else:
                logger.warning(f"Still invalid after local repair: {repaired_validation.errors}")
                # Update the current status to the result of local repair for API repair use
                current_validation = repaired_validation
                current_block = local_result.repaired_block

        # 4. If there are still serious errors, try API repair
        # Note: use current_validation instead of original validation_result
        if current_validation.has_critical_errors() and len(self.llm_repair_fns) > 0:
            logger.info("Local repair fails or is insufficient, try API repair")
            # Pass in local repaired data (if any) to avoid wasting local repair work
            api_result = self.repair_with_api(current_block, current_validation)

            if api_result.success:
                # Verify repair results
                api_repaired_validation = self.validator.validate(api_result.repaired_block)
                if api_repaired_validation.is_valid:
                    logger.info(f"API repair successful: {api_result.changes}")
                    return _cache_and_return(api_result)
                else:
                    logger.warning(f"API still invalid after repair: {api_repaired_validation.errors}")

        # 5. If the original verification passes, return the original or repaired data
        if validation_result.is_valid:
            if local_result.has_changes():
                return _cache_and_return(
                    RepairResult(True, local_result.repaired_block, 'local', local_result.changes)
                )
            else:
                return _cache_and_return(RepairResult(True, widget_block, 'none', []))

        # 6. All repairs fail and the original data (or locally partially repaired data) is returned.
        logger.warning("All repair attempts fail, original data retained")
        # If there is partial repair locally, return the local repaired data (although the verification still fails, it may be better than the original data)
        final_block = local_result.repaired_block if local_result.has_changes() else widget_block
        return _cache_and_return(RepairResult(False, final_block, 'none', []))

    def repair_locally(
        self,
        widget_block: Dict[str, Any],
        validation_result: ValidationResult
    ) -> RepairResult:
        """Fix using local rules.

        Repair rules:
        1. Complete missing basic fields
        2. Fix data type errors
        3. Fix data length mismatch
        4. Clean up invalid data
        5. Add default values"""
        repaired = copy.deepcopy(widget_block)
        changes = []

        # 1. Make sure the basic structure exists
        if 'props' not in repaired or not isinstance(repaired.get('props'), dict):
            repaired['props'] = {}
            changes.append("Add missing props field")

        if 'data' not in repaired or not isinstance(repaired.get('data'), dict):
            repaired['data'] = {}
            changes.append("Add missing data fields")

        # 2. Make sure the chart type exists
        chart_type = self.validator._extract_chart_type(repaired)
        props = repaired['props']

        if not chart_type:
            # Try to infer from widgetType
            widget_type = repaired.get('widgetType', '')
            if '/' in widget_type:
                chart_type = widget_type.split('/')[-1].lower()
                props['type'] = chart_type
                changes.append(f"Infer chart type from widgetType: {chart_type}")
            else:
                # Use bar type by default
                chart_type = 'bar'
                props['type'] = chart_type
                changes.append("Set default chart type: bar")
        elif 'type' not in props or not props['type']:
            # chart_type exists but there is no type field in props and needs to be added
            props['type'] = chart_type
            changes.append(f"Add inferred chart type to props: {chart_type}")

        # 3. Repair data structure
        data = repaired['data']

        # Make sure datasets exist
        if 'datasets' not in data or not isinstance(data.get('datasets'), list):
            data['datasets'] = []
            changes.append("Add missing datasets field")

        # If datasets are empty but there is other data in data, try to construct datasets
        if len(data['datasets']) == 0:
            constructed = self._try_construct_datasets(data, chart_type)
            if constructed:
                data['datasets'] = constructed
                changes.append("Construct datasets from data")
            elif 'labels' in data and isinstance(data.get('labels'), list) and len(data['labels']) > 0:
                # If there are labels but no data, create an empty dataset
                data['datasets'] = [{
                    'label': '数据',
                    'data': [0] * len(data['labels'])
                }]
                changes.append("Create a default dataset based on labels (using zero values)")

        # Make sure labels exist (if needed)
        if chart_type in ChartValidator.LABEL_REQUIRED_TYPES:
            if 'labels' not in data or not isinstance(data.get('labels'), list):
                # Try to generate labels based on the length of datasets
                if data['datasets'] and len(data['datasets']) > 0:
                    first_ds = data['datasets'][0]
                    if isinstance(first_ds, dict) and isinstance(first_ds.get('data'), list):
                        data_len = len(first_ds['data'])
                        data['labels'] = [f"Item {i+1}" for i in range(data_len)]
                        changes.append(f"Generate {data_len} default labels")

        # 4. Repair data in datasets
        for idx, dataset in enumerate(data.get('datasets', [])):
            if not isinstance(dataset, dict):
                continue

            # Make sure there is a data field
            if 'data' not in dataset or not isinstance(dataset.get('data'), list):
                dataset['data'] = []
                changes.append(f"Add an empty data array to datasets[{idx}]")

            # Make sure there is a label
            if 'label' not in dataset:
                dataset['label'] = f"Series {idx + 1}"
                changes.append(f"Add default label for datasets[{idx}]")

            # Fix data length mismatch
            labels = data.get('labels', [])
            ds_data = dataset.get('data', [])
            if isinstance(labels, list) and isinstance(ds_data, list):
                if len(ds_data) < len(labels):
                    # Not enough data, fill in null
                    dataset['data'] = ds_data + [None] * (len(labels) - len(ds_data))
                    changes.append(f"datasets[{idx}] data length is insufficient, add null")
                elif len(ds_data) > len(labels):
                    # Too much data, truncated
                    dataset['data'] = ds_data[:len(labels)]
                    changes.append(f"datasets[{idx}] data length is too long and truncated")

            # Convert non-numeric data to numeric values ​​(if possible)
            if chart_type in ChartValidator.NUMERIC_DATA_TYPES:
                ds_data = dataset.get('data', [])
                converted = False
                for i, value in enumerate(ds_data):
                    if value is None:
                        continue
                    if not isinstance(value, (int, float)):
                        # try to convert
                        try:
                            if isinstance(value, str):
                                # Try converting the string
                                ds_data[i] = float(value)
                                converted = True
                        except (ValueError, TypeError):
                            # Conversion failed, set to null
                            ds_data[i] = None
                            converted = True
                if converted:
                    changes.append(f"datasets[{idx}] contains non-numeric data, conversion has been attempted")

        # 5. Verify the repair results
        success = len(changes) > 0

        return RepairResult(success, repaired, 'local', changes)

    def _try_construct_datasets(
        self,
        data: Dict[str, Any],
        chart_type: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Try constructing datasets from data"""
        # If data directly contains a data array, try to construct
        if 'values' in data and isinstance(data['values'], list):
            return [{
                'label': '数据',
                'data': data['values']
            }]

        # If data contains series field
        if 'series' in data and isinstance(data['series'], list):
            datasets = []
            for idx, series in enumerate(data['series']):
                if isinstance(series, dict):
                    datasets.append({
                        'label': series.get('name', f'系列 {idx + 1}'),
                        'data': series.get('data', [])
                    })
                elif isinstance(series, list):
                    datasets.append({
                        'label': f'系列 {idx + 1}',
                        'data': series
                    })
            if datasets:
                return datasets

        return None

    def repair_with_api(
        self,
        widget_block: Dict[str, Any],
        validation_result: ValidationResult
    ) -> RepairResult:
        """Fix using API (call LLM of 4 Engines).

        Strategy: Try different Engines in sequence until the repair is successful"""
        if not self.llm_repair_fns:
            logger.debug("No LLM repair function available, API repair skipped")
            return RepairResult(False, None, 'api', [])

        widget_id = widget_block.get('widgetId', 'unknown')
        logger.info(f"Chart {widget_id} starts API repair, a total of {len(self.llm_repair_fns)} engines are available")

        for idx, repair_fn in enumerate(self.llm_repair_fns):
            try:
                logger.info(f"Try to use Engine {idx + 1}/{len(self.llm_repair_fns)} to repair chart {widget_id}")
                repaired = repair_fn(widget_block, validation_result.errors)

                if repaired and isinstance(repaired, dict):
                    # Verify repair results
                    repaired_validation = self.validator.validate(repaired)
                    if repaired_validation.is_valid:
                        logger.info(f"Chart {widget_id} is repaired successfully using Engine {idx + 1}")
                        return RepairResult(
                            True,
                            repaired,
                            'api',
                            [f"Repaired successfully using Engine {idx + 1}"]
                        )
                    else:
                        logger.warning(
                            f"Chart {widget_id} Engine {idx + 1} Data returned failed validation:"
                            f"{repaired_validation.errors}"
                        )
                else:
                    logger.warning(f"Chart {widget_id} Engine {idx + 1} returns empty or invalid response")
            except Exception as e:
                # Use exception to log the complete stack
                logger.exception(f"Chart {widget_id} Engine {idx + 1} Exception occurred during repair: {e}")
                continue

        logger.warning(f"Chart {widget_id} All {len(self.llm_repair_fns)} engines failed to be repaired")
        return RepairResult(False, None, 'api', [])


def create_chart_validator() -> ChartValidator:
    """Create a chart validator instance"""
    return ChartValidator()


def create_chart_repairer(
    validator: Optional[ChartValidator] = None,
    llm_repair_fns: Optional[List[Callable]] = None
) -> ChartRepairer:
    """Create a chart fixer instance"""
    if validator is None:
        validator = create_chart_validator()
    return ChartRepairer(validator, llm_repair_fns)
