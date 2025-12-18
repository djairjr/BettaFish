"""Chart to SVG Converter - Convert Chart.js data to vector SVG graphics

Supported chart types:
- line: line chart
- bar: bar chart
- pie: pie chart
- donut: donut chart
- radar: radar chart
- polarArea: polar area map
- scatter: scatter plot"""

from __future__ import annotations

import base64
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

try:
    import matplotlib
    matplotlib.use('Agg')  # Use a non-GUI backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.font_manager as fm
    from matplotlib.patches import Wedge, Rectangle
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("Matplotlib is not installed, PDF chart vector rendering functionality will not be available")

# Optional dependency: scipy for curve smoothing
try:
    from scipy.interpolate import make_interp_spline
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.info("If Scipy is not installed, the line chart will not support the curve smoothing function (does not affect basic rendering)")


class ChartToSVGConverter:
    """Convert Chart.js chart data to SVG vector graphics"""

    # Default color palette (optimized version: bright and easy to distinguish)
    DEFAULT_COLORS = [
        '# 4A90E2', '#E85D75', '#50C878', '#FFB347', # bright blue, coral red, emerald green, orange
        '# 9B59B6', '#3498DB', '#E67E22', '#16A085', # purple, sky blue, orange, cyan
        '# F39C12', '#D35400', '#27AE60', '#8E44AD' # gold, dark orange, green, violet
    ]

    # CSS variable to color mapping table (optimized version: use brighter, lighter colors)
    CSS_VAR_COLOR_MAP = {
        'var(--color-accent)': '# 4A90E2', # bright blue (changed from #007AFF to lighter)
        'var(--re-accent-color)': '# 4A90E2', # bright blue
        'var(--re-accent-color-translucent)': (0.29, 0.565, 0.886, 0.08),  # Blue very light transparent rgba(74, 144, 226, 0.08)
        'var(--color-kpi-down)': '# E85D75', #coral red (changed from #DC3545 to softer)
        'var(--re-danger-color)': '# E85D75', #coral red
        'var(--re-danger-color-translucent)': (0.91, 0.365, 0.459, 0.08),  # Red extremely light transparent rgba(232, 93, 117, 0.08)
        'var(--color-warning)': '# FFB347', # soft orange (changed from #FFC107 to lighter)
        'var(--re-warning-color)': '# FFB347', #soft orange yellow
        'var(--re-warning-color-translucent)': (1.0, 0.702, 0.278, 0.08),  # Yellow very light transparent rgba(255, 179, 71, 0.08)
        'var(--color-success)': '# 50C878', # emerald green (changed from #28A745 to brighter)
        'var(--re-success-color)': '# 50C878', # emerald green
        'var(--re-success-color-translucent)': (0.314, 0.784, 0.471, 0.08),  # Green very light transparent rgba(80, 200, 120, 0.08)
        'var(--color-accent-positive)': '#50C878',
        'var(--color-accent-negative)': '#E85D75',
        'var(--color-text-secondary)': '#6B7280',
        'var(--accentPositive)': '#50C878',
        'var(--accentNegative)': '#E85D75',
        'var(--sentiment-positive, #28A745)': '#28A745',
        'var(--sentiment-negative, #E53E3E)': '#E53E3E',
        'var(--sentiment-neutral, #FFC107)': '#FFC107',
        'var(--sentiment-positive)': '#28A745',
        'var(--sentiment-negative)': '#E53E3E',
        'var(--sentiment-neutral)': '#FFC107',
        'var(--color-primary)': '# 3498DB', # sky blue
        'var(--color-secondary)': '# 95A5A6', # light gray
    }

    # Supports parsing rgba(var(--color-primary-rgb), 0.5) and other formats such as rgba(var(--color-primary-rgb), 0.5)
    CSS_VAR_RGB_MAP = {
        'color-primary-rgb': (52, 152, 219),
        'color-tone-up-rgb': (80, 200, 120),
        'color-tone-down-rgb': (232, 93, 117),
        'color-accent-positive-rgb': (80, 200, 120),
        'color-accent-neutral-rgb': (149, 165, 166),
    }

    def __init__(self, font_path: Optional[str] = None):
        """Initialize converter

        Parameters:
            font_path: Chinese font path (optional)"""
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("Matplotlib is not installed, please run: pip install matplotlib")

        self.font_path = font_path
        self._setup_chinese_font()

    def _setup_chinese_font(self):
        """Configure Chinese fonts"""
        if self.font_path:
            try:
                # Add custom font
                fm.fontManager.addfont(self.font_path)
                # Set default font
                font_prop = fm.FontProperties(fname=self.font_path)
                plt.rcParams['font.family'] = font_prop.get_name()
                plt.rcParams['axes.unicode_minus'] = False  # Solve the problem of negative sign display
                logger.info(f"Loaded Chinese font: {self.font_path}")
            except Exception as e:
                logger.warning(f"Failed to load Chinese font: {e}, system default font will be used")
        else:
            # Try using system Chinese fonts
            try:
                plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
            except Exception as e:
                logger.warning(f"Failed to configure Chinese font: {e}")

    def convert_widget_to_svg(
        self,
        widget_data: Dict[str, Any],
        width: int = 800,
        height: int = 500,
        dpi: int = 100
    ) -> Optional[str]:
        """Convert widget data to SVG string

        Parameters:
            widget_data: widget block data (including widgetType, data, props)
            width: chart width (pixels)
            height: chart height (pixels)
            dpi: DPI settings

        Return:
            str: SVG string, returns None on failure"""
        try:
            # Extract chart type
            widget_type = widget_data.get('widgetType', '')
            if not widget_type or not widget_type.startswith('chart.js'):
                logger.warning(f"Unsupported widget type: {widget_type}")
                return None

            # Extract the chart type from widgetType, for example "chart.js/line" -> "line"
            chart_type = widget_type.split('/')[-1] if '/' in widget_type else 'bar'

            # Also check the type in props
            props = widget_data.get('props', {})
            if props.get('type'):
                chart_type = props['type']

            # Chart.js v4 has removed the horizontalBar type, which is automatically downgraded to bar and set horizontal coordinates
            horizontal_bar = False
            if chart_type and str(chart_type).lower() == 'horizontalbar':
                chart_type = 'bar'
                horizontal_bar = True

            # Supports forcing horizontal histogram via indexAxis: 'y'
            if isinstance(props, dict):
                options = props.get('options') or {}
                index_axis = (options.get('indexAxis') or props.get('indexAxis') or '').lower()
                if index_axis == 'y':
                    horizontal_bar = True

            # Extract data
            data = widget_data.get('data', {})
            if not data:
                logger.warning("Chart data is empty")
                return None

            # Call the corresponding rendering method according to the chart type
            if 'wordcloud' in str(chart_type).lower():
                # Word clouds are processed by dedicated rendering logic, SVG conversion is skipped here to avoid warnings
                logger.debug("Word cloud chart detected, skipping chart_to_svg conversion")
                return None

            # Dispatch rendering method, special handling of horizontal histograms
            if chart_type == 'bar':
                return self._render_bar(data, props, width, height, dpi, horizontal=horizontal_bar)
            elif chart_type == 'bubble':
                return self._render_bubble(data, props, width, height, dpi)
            else:
                render_method = getattr(self, f'_render_{chart_type}', None)
                if not render_method:
                    logger.warning(f"Unsupported chart type: {chart_type}")
                    return None

            # Create charts and convert to SVG
            return render_method(data, props, width, height, dpi)

        except Exception as e:
            logger.error(f"Converting chart to SVG failed: {e}", exc_info=True)
            return None

    def _create_figure(
        self,
        width: int,
        height: int,
        dpi: int,
        title: Optional[str] = None
    ) -> Tuple[Any, Any]:
        """Create matplotlib charts

        Return:
            tuple: (fig, ax)"""
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)

        if title:
            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        return fig, ax

    def _parse_color(self, color: Any) -> Any:
        """Parse color values and convert CSS format to format supported by matplotlib

        Parameters:
            color: color value (may be CSS format such as rgba() or hexadecimal or CSS variable)

        Return:
            Color formats supported by matplotlib (hex string or RGB(A) tuple)"""
        if color is None:
            return None

        # Process numpy arrays and convert them into native lists
        _np = globals().get("np")
        if _np is not None and hasattr(_np, "ndarray") and isinstance(color, _np.ndarray):
            color = color.tolist()

        # Directly and transparently transmit the color that is already a sequence (such as (r,g,b,a)) to avoid invalidation after being converted into a string.
        if isinstance(color, (list, tuple)):
            if len(color) in (3, 4) and all(isinstance(c, (int, float)) for c in color):
                normalized = []
                for idx, channel in enumerate(color):
                    # Matplotlib accepts floating point numbers between 0-1. If the value is >1, it will be normalized according to the source of 0-255.
                    value = float(channel)
                    if value > 1:
                        value = value / 255.0
                    # Only the RGB channel is forced to be clipped, and the alpha is clipped according to 0-1.
                    if idx < 3:
                        value = max(0.0, min(value, 1.0))
                    else:
                        value = max(0.0, min(value, 1.0))
                    normalized.append(value)
                return tuple(normalized)

            try:
                return tuple(color)
            except Exception:
                return color

        # The remaining non-string types maintain the original string fallback policy
        if not isinstance(color, str):
            return str(color)

        color = color.strip()

        # Process rgba(var(--color-primary-rgb), 0.5) / rgb(var(--color-primary-rgb))
        var_rgba_pattern = r'rgba?\(var\(--([\w-]+)\)\s*(?:,\s*([\d.]+))?\)'
        match = re.match(var_rgba_pattern, color)
        if match:
            var_name, alpha_str = match.groups()
            rgb_tuple = self.CSS_VAR_RGB_MAP.get(var_name)

            # Compatible with writing methods that lack the -rgb suffix
            if not rgb_tuple:
                if var_name.endswith('-rgb'):
                    rgb_tuple = self.CSS_VAR_RGB_MAP.get(var_name[:-4])
                else:
                    rgb_tuple = self.CSS_VAR_RGB_MAP.get(f"{var_name}-rgb")

            if rgb_tuple:
                r, g, b = rgb_tuple
                alpha = float(alpha_str) if alpha_str is not None else 1.0
                return (r / 255, g / 255, b / 255, alpha)

        # [Enhancement] Handle CSS variables, such as var(--color-accent)
        # Use predefined color maps instead of CSS variables to ensure different variables have different colors
        if color.startswith('var('):
            # Parse var(--token, fallback) form
            fb_match = re.match(r'^var\(\s*--[^,)+]+,\s*([^)]+)\)', color)
            if fb_match:
                fb_raw = fb_match.group(1).strip()
                fb_color = self._parse_color(fb_raw)
                if fb_color:
                    return fb_color
            # Try to find the corresponding color from the mapping table
            mapped_color = self.CSS_VAR_COLOR_MAP.get(color)
            if mapped_color:
                return mapped_color
            # If not in the mapping table, try to infer the color type from the variable name
            if 'accent' in color or 'primary' in color:
                return '# 007AFF' # blue
            elif 'danger' in color or 'down' in color or 'error' in color:
                return '# DC3545' # red
            elif 'warning' in color:
                return '# FFC107' # yellow
            elif 'success' in color or 'up' in color:
                return '# 28A745' # green
            # Returns blue by default
            return '#36A2EB'

        # Process rgba(r, g, b, a) format
        rgba_pattern = r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)'
        match = re.match(rgba_pattern, color)
        if match:
            r, g, b, a = match.groups()
            # Convert to matplotlib format (r/255, g/255, b/255, a)
            return (int(r)/255, int(g)/255, int(b)/255, float(a))

        # Process rgb(r, g, b) format
        rgb_pattern = r'rgb\((\d+),\s*(\d+),\s*(\d+)\)'
        match = re.match(rgb_pattern, color)
        if match:
            r, g, b = match.groups()
            # Convert to matplotlib format (r/255, g/255, b/255)
            return (int(r)/255, int(g)/255, int(b)/255)

        # Other formats (hexadecimal, color name, etc.) are returned directly
        return color

    def _ensure_visible_color(self, color: Any, fallback: str, min_alpha: float = 0.6) -> Any:
        """Make sure colors are visible when rendering: avoid transparency values ​​and raise opacity that is too low"""
        base_color = fallback if color in (None, "", "transparent") else color
        parsed = self._parse_color(base_color)
        fallback_parsed = self._parse_color(fallback)

        if isinstance(parsed, tuple):
            if len(parsed) == 4:
                r, g, b, a = parsed
                return (r, g, b, max(a, min_alpha))
            return parsed

        if isinstance(parsed, str) and parsed.lower() == "transparent":
            return fallback_parsed

        return parsed if parsed is not None else fallback_parsed

    def _get_colors(self, datasets: List[Dict[str, Any]]) -> List[str]:
        """Get chart color

        The colors defined in the dataset are used first, otherwise the default palette is used."""
        colors = []
        for i, dataset in enumerate(datasets):
            # Try to get every possible color field
            color = (
                dataset.get('backgroundColor') or
                dataset.get('borderColor') or
                dataset.get('color') or
                self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
            )

            # If it is a color array, take the first one
            if isinstance(color, list):
                color = color[0] if color else self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]

            # Parse color format
            color = self._parse_color(color)

            colors.append(color)

        return colors

    def _align_labels_and_data(
        self,
        labels: Any,
        dataset_data: Any,
        chart_type: str,
        require_positive_sum: bool = False
    ) -> Tuple[List[str], List[float]]:
        """Align labels and data lengths for categorical charts, and clean non-numeric values.

        Matplotlib's pie chart/donut chart requires labels to be consistent with the data length, otherwise an error will be thrown."""
        original_label_len = len(labels) if isinstance(labels, list) else 0
        original_data_len = len(dataset_data) if isinstance(dataset_data, list) else 0

        aligned_labels = [str(label) for label in labels] if isinstance(labels, list) else []
        raw_data = dataset_data if isinstance(dataset_data, list) else []

        cleaned_data: List[float] = []
        for value in raw_data:
            try:
                numeric = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                numeric = 0.0
            if numeric < 0:
                numeric = 0.0
            cleaned_data.append(numeric)

        target_len = max(len(aligned_labels), len(cleaned_data))
        if target_len == 0:
            return [], []

        if len(aligned_labels) < target_len:
            start = len(aligned_labels)
            aligned_labels.extend([f"Unnamed {start + idx + 1}" for idx in range(target_len - start)])

        if len(cleaned_data) < target_len:
            cleaned_data.extend([0.0] * (target_len - len(cleaned_data)))

        if original_label_len != original_data_len:
            logger.warning(
                f"The {chart_type} chart labels length ({original_label_len}) is inconsistent with the data length ({original_data_len})."
                f"Aligned to {target_len}"
            )

        if require_positive_sum and not any(value > 0 for value in cleaned_data):
            logger.warning(f"{chart_type} chart data is empty, skip rendering")
            return [], []

        return aligned_labels[:target_len], cleaned_data[:target_len]

    def _figure_to_svg(self, fig: Any) -> str:
        """Convert matplotlib chart to SVG string"""
        svg_buffer = io.BytesIO()
        fig.savefig(svg_buffer, format='svg', bbox_inches='tight', transparent=False, facecolor='white')
        plt.close(fig)

        svg_buffer.seek(0)
        svg_string = svg_buffer.getvalue().decode('utf-8')

        return svg_string

    def _render_line(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render a line chart (enhanced version)

        Supported features:
        - Multiple y-axes (yAxisID: 'y', 'y1', 'y2', 'y3'...)
        - fill area (fill: true)
        - Transparency (alpha channel in backgroundColor)
        - Line style (tension curve smoothing)"""
        try:
            labels = data.get('labels') or []
            datasets = data.get('datasets') or []

            has_object_points = any(
                isinstance(ds, dict)
                and isinstance(ds.get('data'), list)
                and any(isinstance(pt, dict) and ('x' in pt or 'y' in pt) for pt in ds.get('data'))
                for ds in datasets
            )

            if (not datasets) or ((not labels) and not has_object_points):
                return None

            # Collect all unique yAxisIDs
            y_axis_ids = []
            for dataset in datasets:
                y_axis_id = dataset.get('yAxisID', 'y')
                if y_axis_id not in y_axis_ids:
                    y_axis_ids.append(y_axis_id)

            # Make sure 'y' is the first axis
            if 'y' in y_axis_ids:
                y_axis_ids.remove('y')
                y_axis_ids.insert(0, 'y')

            # Check if there are multiple y-axes
            has_multiple_axes = len(y_axis_ids) > 1

            title = props.get('title')
            options = props.get('options', {})
            scales = options.get('scales', {})
            x_tick_labels = list(labels) if isinstance(labels, list) else []

            # Create a chart and multiple y-axes
            fig, ax1 = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)

            if title:
                ax1.set_title(title, fontsize=14, fontweight='bold', pad=20)

            # Create y-axis mapping dictionary
            axes = {'y': ax1}

            if has_multiple_axes:
                # Count the number of axes at each position (left/right) and use it to calculate the offset
                left_axes_count = 0
                right_axes_count = 0

                # Create new y-axis for each additional yAxisID
                for y_axis_id in y_axis_ids[1:]:
                    if y_axis_id == 'y':
                        continue

                    # Create new y-axis
                    new_ax = ax1.twinx()
                    axes[y_axis_id] = new_ax

                    # Get axis position from scales configuration
                    y_config = scales.get(y_axis_id, {})
                    position = y_config.get('position', 'right')

                    if position == 'left':
                        # Extra axis on the left, offset to the left
                        if left_axes_count > 0:
                            new_ax.spines['left'].set_position(('outward', 60 * left_axes_count))
                        new_ax.yaxis.set_label_position('left')
                        new_ax.yaxis.set_ticks_position('left')
                        left_axes_count += 1
                    else:
                        # Extra axis on the right, offset to the right
                        if right_axes_count > 0:
                            new_ax.spines['right'].set_position(('outward', 60 * right_axes_count))
                        right_axes_count += 1

            colors = self._get_colors(datasets)

            # Collect line and fill information for each y-axis for use in legend
            axis_lines = {axis_id: [] for axis_id in y_axis_ids}
            legend_handles = []  # legend handle
            legend_labels = []   # legend labels

            # Plot each data series
            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'系列{i+1}')
                color = colors[i]

                # Get configuration
                y_axis_id = dataset.get('yAxisID', 'y')
                fill = True  # Force filling on for easy comparison
                tension = dataset.get('tension', 0)  # 0 represents a straight line, 0.4 represents a smooth curve
                border_color = self._parse_color(dataset.get('borderColor', color))
                background_color = self._parse_color(dataset.get('backgroundColor', color))

                # Select the corresponding coordinate axis
                ax = axes.get(y_axis_id, ax1)

                is_object_data = isinstance(dataset_data, list) and any(
                    isinstance(point, dict) and ('x' in point or 'y' in point)
                    for point in dataset_data
                )

                if is_object_data:
                    x_data = []
                    y_data = []
                    annotations = []

                    for idx, point in enumerate(dataset_data):
                        if not isinstance(point, dict):
                            continue

                        label_text = str(point.get('x', f"Point {idx + 1}"))
                        if len(x_tick_labels) < len(dataset_data):
                            x_tick_labels.append(label_text)

                        x_data.append(len(x_data))

                        y_val = point.get('y', 0)
                        try:
                            y_val = float(y_val)
                        except (TypeError, ValueError):
                            y_val = 0
                        y_data.append(y_val)
                        annotations.append(point.get('event'))

                    if not x_data:
                        continue

                    line, = ax.plot(x_data, y_data, marker='o', label=label,
                                    color=border_color, linewidth=2, markersize=6)

                    if fill:
                        ax.fill_between(x_data, y_data, alpha=0.2, color=background_color)

                    for pos, y_val, text in zip(x_data, y_data, annotations):
                        if text:
                            ax.annotate(
                                text,
                                (pos, y_val),
                                textcoords='offset points',
                                xytext=(0, 8),
                                ha='center',
                                fontsize=8,
                                rotation=20
                            )
                else:
                    # Draw polyline
                    x_data = range(len(labels))

                    # Determine whether to smooth based on the tension value
                    if tension > 0 and SCIPY_AVAILABLE:
                        # Smooth curves using spline interpolation (requires scipy)
                        if len(dataset_data) >= 4:  # At least 4 points are needed for smoothing
                            try:
                                x_smooth = np.linspace(0, len(labels)-1, len(labels)*3)
                                spl = make_interp_spline(x_data, dataset_data, k=min(3, len(dataset_data)-1))
                                y_smooth = spl(x_smooth)
                                line, = ax.plot(x_smooth, y_smooth, label=label, color=border_color, linewidth=2)

                                # If padding is required (use very low opacity to avoid occlusion)
                                if fill:
                                    ax.fill_between(x_smooth, y_smooth, alpha=0.2, color=background_color)
                            except:
                                # If smoothing fails, use a normal polyline
                                line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                              color=border_color, linewidth=2, markersize=6)
                                if fill:
                                    ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)
                        else:
                            line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                          color=border_color, linewidth=2, markersize=6)
                            if fill:
                                ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)
                    else:
                        # Straight line connection (tension=0 or scipy is not available)
                        line, = ax.plot(x_data, dataset_data, marker='o', label=label,
                                      color=border_color, linewidth=2, markersize=6)

                        # If padding is required (use very low opacity to avoid occlusion)
                        if fill:
                            ax.fill_between(x_data, dataset_data, alpha=0.2, color=background_color)

                # Record which axis this line belongs to
                axis_lines[y_axis_id].append(line)

                # Create legend item: If there is padding, create a legend with a padded background
                if fill:
                    # Create a rectangular patch as the fill background (use slightly higher transparency so it is visible in the legend)
                    fill_patch = Rectangle((0, 0), 1, 1,
                                          facecolor=background_color,
                                          edgecolor='none',
                                          alpha=0.15)
                    # Combine line and fill patches
                    legend_handles.append((line, fill_patch))
                    legend_labels.append(label)
                else:
                    legend_handles.append(line)
                    legend_labels.append(label)

            # Set x-axis labels
            if x_tick_labels:
                ax1.set_xticks(range(len(x_tick_labels)))
                ax1.set_xticklabels(x_tick_labels, rotation=45, ha='right')

            # Set y-axis labels and titles
            for y_axis_id, ax in axes.items():
                y_config = scales.get(y_axis_id, {})
                y_title = y_config.get('title', {}).get('text', '')

                if y_title:
                    ax.set_ylabel(y_title, fontsize=11)

                # Set the y-axis label color (if the axis has only one line, use the color of that line)
                if len(axis_lines[y_axis_id]) == 1:
                    line_color = axis_lines[y_axis_id][0].get_color()
                    ax.tick_params(axis='y', labelcolor=line_color)
                    ax.yaxis.label.set_color(line_color)

            # Set the grid (only displayed on the main axis)
            ax1.grid(True, alpha=0.3, linestyle='--')
            for y_axis_id in y_axis_ids[1:]:
                if y_axis_id in axes:
                    axes[y_axis_id].grid(False)

            # Create a legend
            if has_multiple_axes or len(datasets) > 1:
                # Use custom legend_handles and legend_labels
                from matplotlib.legend_handler import HandlerTuple

                ax1.legend(legend_handles, legend_labels,
                          loc='best',
                          framealpha=0.9,
                          handler_map={tuple: HandlerTuple(ndivide=None)})

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render line chart: {e}", exc_info=True)
            return None

    def _render_bar(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int,
        horizontal: bool = False
    ) -> Optional[str]:
        """Render histogram (supports horizontal barh)"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            colors = self._get_colors(datasets)

            # Calculate column position
            positions = np.arange(len(labels))
            width_bar = 0.8 / len(datasets) if len(datasets) > 1 else 0.6

            # Draw horizontally/vertically
            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'系列{i+1}')
                color = colors[i]

                offset = (i - len(datasets)/2 + 0.5) * width_bar

                if horizontal:
                    ax.barh(
                        positions + offset,
                        dataset_data,
                        height=width_bar,
                        label=label,
                        color=color,
                        alpha=0.8,
                        edgecolor='white',
                        linewidth=0.5
                    )
                else:
                    ax.bar(
                        positions + offset,
                        dataset_data,
                        width_bar,
                        label=label,
                        color=color,
                        alpha=0.8,
                        edgecolor='white',
                        linewidth=0.5
                    )

            # axis labels/grid
            if horizontal:
                ax.set_yticks(positions)
                ax.set_yticklabels(labels)
                ax.invert_yaxis()  # Consistent with Chart.js horizontal arrangement
                ax.grid(True, alpha=0.3, linestyle='--', axis='x')
            else:
                ax.set_xticks(positions)
                ax.set_xticklabels(labels, rotation=45, ha='right')
                ax.grid(True, alpha=0.3, linestyle='--', axis='y')

            # Show legend
            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render histogram: {e}")
            return None

    def _render_bubble(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render bubble chart"""
        try:
            datasets = data.get('datasets', [])
            if not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)
            colors = self._get_colors(datasets)

            def _safe_radius(raw) -> float:
                """Safely convert the input radius to floating point and set a minimum threshold to avoid bubbles disappearing completely"""
                try:
                    val = float(raw)
                    return max(val, 0.5)
                except Exception:
                    return 1.0

            all_x: list[float] = []
            all_y: list[float] = []
            max_r: float = 0.0

            for i, dataset in enumerate(datasets):
                points = dataset.get('data', [])
                label = dataset.get('label', f'系列{i+1}')
                color = colors[i]

                if points and isinstance(points[0], dict):
                    xs = [p.get('x', 0) for p in points]
                    ys = [p.get('y', 0) for p in points]
                    rs = [_safe_radius(p.get('r', 1)) for p in points]
                else:
                    xs = list(range(len(points)))
                    ys = points
                    rs = [1.0 for _ in points]

                all_x.extend(xs)
                all_y.extend(ys)
                if rs:
                    max_r = max(max_r, max(rs))

                # Moderately enlarge the radius, approximate Chart.js pixel size (dynamic scale, avoid excessive occlusion)
                size_scale = 8.0 if max_r <= 20 else 6.5
                sizes = [(r * size_scale) ** 2 for r in rs]

                ax.scatter(
                    xs,
                    ys,
                    s=sizes,
                    label=label,
                    color=color,
                    alpha=0.45,
                    edgecolors='white',
                    linewidth=0.6
                )

            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)

            # Leave appropriate white space to prevent large bubbles from being cut.
            if all_x and all_y:
                x_min, x_max = min(all_x), max(all_x)
                y_min, y_max = min(all_y), max(all_y)
                x_span = max(x_max - x_min, 1e-6)
                y_span = max(y_max - y_min, 1e-6)
                pad_x = max(x_span * 0.12, max_r * 1.2)
                pad_y = max(y_span * 0.12, max_r * 1.2)
                ax.set_xlim(x_min - pad_x, x_max + pad_x)
                ax.set_ylim(y_min - pad_y, y_max + pad_y)
                # extra safety margin
                ax.margins(x=0.05, y=0.05)

            ax.grid(True, alpha=0.3, linestyle='--')
            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render bubble chart: {e}", exc_info=True)
            return None

    def _render_pie(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Rendering a pie chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            # Pie chart only uses the first data set
            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="cake",
                require_positive_sum=True
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            # Get color
            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]

            # Draw a pie chart
            wedges, texts, autotexts = ax.pie(
                dataset_data,
                labels=labels,
                colors=colors,
                autopct='%1.1f%%',
                startangle=90,
                textprops={'fontsize': 10}
            )

            # Set percentage text to white
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            ax.axis('equal')  # keep round

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render pie chart: {e}")
            return None

    def _render_doughnut(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render a donut chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            # Donut chart only uses the first data set
            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="ring",
                require_positive_sum=True
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            # Get color
            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]

            # Draw a donut chart (achieving a hollow effect by setting wedgeprops)
            wedges, texts, autotexts = ax.pie(
                dataset_data,
                labels=labels,
                colors=colors,
                autopct='%1.1f%%',
                startangle=90,
                wedgeprops=dict(width=0.5, edgecolor='white'),
                textprops={'fontsize': 10}
            )

            # Set percentage text
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')

            ax.axis('equal')

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render donut chart: {e}")
            return None

    def _render_radar(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render radar chart"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            title = props.get('title')
            fig = plt.figure(figsize=(width/dpi, height/dpi), dpi=dpi)

            # Create a polar subplot
            ax = fig.add_subplot(111, projection='polar')

            if title:
                ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            colors = self._get_colors(datasets)

            # Calculate angle
            angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
            angles += angles[:1]  # closed shape

            # Plot each data series
            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'系列{i+1}')
                color = colors[i]

                # closed data
                values = dataset_data + dataset_data[:1]

                # Draw a radar chart
                ax.plot(angles, values, 'o-', linewidth=2, label=label, color=color)
                ax.fill(angles, values, alpha=0.25, color=color)

            # Set label
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(labels)

            # Show legend
            if len(datasets) > 1:
                ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render radar chart: {e}")
            return None

    def _render_scatter(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Render a scatter plot"""
        try:
            datasets = data.get('datasets', [])

            if not datasets:
                return None

            title = props.get('title')
            fig, ax = self._create_figure(width, height, dpi, title)

            colors = self._get_colors(datasets)

            # Plot each data series
            for i, dataset in enumerate(datasets):
                dataset_data = dataset.get('data', [])
                label = dataset.get('label', f'系列{i+1}')
                color = colors[i]

                # Extract x and y coordinates
                if dataset_data and isinstance(dataset_data[0], dict):
                    x_values = [point.get('x', 0) for point in dataset_data]
                    y_values = [point.get('y', 0) for point in dataset_data]
                else:
                    # If not in {x,y} format, use index as x
                    x_values = range(len(dataset_data))
                    y_values = dataset_data

                ax.scatter(
                    x_values,
                    y_values,
                    label=label,
                    color=color,
                    s=50,
                    alpha=0.6,
                    edgecolors='white',
                    linewidth=0.5
                )

            # Show legend
            if len(datasets) > 1:
                ax.legend(loc='best', framealpha=0.9)

            # grid
            ax.grid(True, alpha=0.3, linestyle='--')

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render scatterplot: {e}")
            return None

    def _render_polarArea(
        self,
        data: Dict[str, Any],
        props: Dict[str, Any],
        width: int,
        height: int,
        dpi: int
    ) -> Optional[str]:
        """Rendering a map of the polar regions"""
        try:
            labels = data.get('labels', [])
            datasets = data.get('datasets', [])

            if not labels or not datasets:
                return None

            # Only use the first dataset
            dataset = datasets[0]
            dataset_data = dataset.get('data', [])

            labels, dataset_data = self._align_labels_and_data(
                labels,
                dataset_data,
                chart_type="polar regions",
                require_positive_sum=False
            )

            if not labels or not dataset_data:
                return None

            title = props.get('title')
            fig = plt.figure(figsize=(width/dpi, height/dpi), dpi=dpi)
            ax = fig.add_subplot(111, projection='polar')

            if title:
                ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            # Get color
            raw_colors = dataset.get('backgroundColor', self.DEFAULT_COLORS[:len(labels)])
            if not isinstance(raw_colors, list):
                raw_colors = self.DEFAULT_COLORS[:len(labels)]

            colors = [
                self._ensure_visible_color(
                    raw_colors[i] if i < len(raw_colors) else None,
                    self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                )
                for i in range(len(labels))
            ]

            # Calculate angle
            theta = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
            width_bar = 2 * np.pi / len(labels)

            # Map the polar regions
            bars = ax.bar(
                theta,
                dataset_data,
                width=width_bar,
                bottom=0.0,
                color=colors,
                alpha=0.7,
                edgecolor='white',
                linewidth=1
            )

            # Set label
            ax.set_xticks(theta)
            ax.set_xticklabels(labels)

            return self._figure_to_svg(fig)

        except Exception as e:
            logger.error(f"Failed to render polar region map: {e}")
            return None


def create_chart_converter(font_path: Optional[str] = None) -> ChartToSVGConverter:
    """Create a chart converter instance

    Parameters:
        font_path: Chinese font path (optional)

    Return:
        ChartToSVGConverter: Converter instance"""
    return ChartToSVGConverter(font_path=font_path)


__all__ = ["ChartToSVGConverter", "create_chart_converter"]
