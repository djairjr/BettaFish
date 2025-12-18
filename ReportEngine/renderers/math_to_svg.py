"""LaTeX mathematical formula to SVG renderer
Render LaTeX equations to SVG format for PDF export using matplotlib"""

import io
import re
from typing import Optional
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import mathtext
from loguru import logger

# Use a non-interactive backend
matplotlib.use('Agg')


class MathToSVG:
    """Converter for LaTeX math formulas to SVG"""

    def __init__(self, font_size: int = 14, color: str = 'black'):
        """Initialize formula converter

        Args:
            font_size: font size (points)
            color: text color"""
        self.font_size = font_size
        self.color = color

    def convert_to_svg(self, latex: str, display_mode: bool = True) -> Optional[str]:
        """Convert LaTeX formula to SVG string

        Args:
            latex: LaTeX formula string (without $$ or $ symbols)
            display_mode: True is display mode (block-level formula), False is inline mode

        Returns:
            SVG string, or None if conversion fails"""
        try:
            # Clean LaTeX strings, remove outer delimiters, compatible with $...$ / $$...$$ / \\( \\) / \\[ \\]
            latex = (latex or "").strip()
            patterns = [
                r'^\$\$(.*)\$\$$',
                r'^\$(.*)\$$',
                r'^\\\[(.*)\\\]$',
                r'^\\\((.*)\\\)$',
            ]
            for pat in patterns:
                m = re.match(pat, latex, re.DOTALL)
                if m:
                    latex = m.group(1).strip()
                    break
            # Clean up control characters and make common compatibility
            latex = re.sub(r'[\x00-\x1f\x7f]', '', latex)
            latex = latex.replace(r'\\tfrac', r'\\frac').replace(r'\\dfrac', r'\\frac')
            if not latex:
                logger.warning("Empty LaTeX formula")
                return None

            # Create graphics
            fig = plt.figure(figsize=(10, 2) if display_mode else (6, 1))
            fig.patch.set_alpha(0)  # Transparent background

            # Rendering LaTeX
            # Rendering using mathtext
            if display_mode:
                # Display mode: Centered, larger font
                text = fig.text(
                    0.5, 0.5,
                    f'${latex}$',
                    fontsize=self.font_size * 1.2,
                    color=self.color,
                    ha='center',
                    va='center',
                    usetex=False  # Use matplotlib's built-in mathtext instead of full LaTeX
                )
            else:
                # Inline mode: left justified, normal font
                text = fig.text(
                    0.1, 0.5,
                    f'${latex}$',
                    fontsize=self.font_size,
                    color=self.color,
                    ha='left',
                    va='center',
                    usetex=False
                )

            # Get text bounding box
            fig.canvas.draw()
            bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())

            # Convert to inches (the unit used by matplotlib)
            bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())

            # Resize graphics to fit text, add margins
            margin = 0.1  # inch
            fig.set_size_inches(
                bbox_inches.width + 2 * margin,
                bbox_inches.height + 2 * margin
            )

            # Reposition text to center
            text.set_position((0.5, 0.5))

            # Save as SVG
            svg_buffer = io.StringIO()
            plt.savefig(
                svg_buffer,
                format='svg',
                bbox_inches='tight',
                pad_inches=0.1,
                transparent=True,
                dpi=300
            )
            plt.close(fig)

            # Get SVG content
            svg_content = svg_buffer.getvalue()
            svg_buffer.close()

            return svg_content

        except Exception as e:
            logger.error(f"LaTeX formula conversion failed: {latex[:100]}... Error: {str(e)}")
            return None

    def convert_inline_to_svg(self, latex: str) -> Optional[str]:
        """Convert inline LaTeX formulas to SVG

        Args:
            latex: LaTeX formula string

        Returns:
            SVG string, or None if conversion fails"""
        return self.convert_to_svg(latex, display_mode=False)

    def convert_display_to_svg(self, latex: str) -> Optional[str]:
        """Convert display mode LaTeX equations to SVG

        Args:
            latex: LaTeX formula string

        Returns:
            SVG string, or None if conversion fails"""
        return self.convert_to_svg(latex, display_mode=True)


def convert_math_block_to_svg(
    latex: str,
    font_size: int = 16,
    color: str = 'black'
) -> Optional[str]:
    """Convenience function: convert blocks of math formulas to SVG

    Args:
        latex: LaTeX formula string
        font_size: font size
        color: text color

    Returns:
        SVG string, or None if conversion fails"""
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_display_to_svg(latex)


def convert_math_inline_to_svg(
    latex: str,
    font_size: int = 14,
    color: str = 'black'
) -> Optional[str]:
    """Convenience function: Convert inline math formulas to SVG

    Args:
        latex: LaTeX formula string
        font_size: font size
        color: text color

    Returns:
        SVG string, or None if conversion fails"""
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_inline_to_svg(latex)


if __name__ == "__main__":
    # test code
    import sys

    # test formula
    test_formulas = [
        r"E = mc^2",
        r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        r"\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}",
        r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}",
    ]

    converter = MathToSVG(font_size=16)

    for i, formula in enumerate(test_formulas):
        logger.info(f"Test formula {i+1}: {formula}")
        svg = converter.convert_display_to_svg(formula)
        if svg:
            # save to file
            filename = f"test_math_{i+1}.svg"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(svg)
            logger.info(f"Successfully saved to {filename}")
        else:
            logger.error(f"Formula {i+1} conversion failed")

    logger.info("Test completed")
