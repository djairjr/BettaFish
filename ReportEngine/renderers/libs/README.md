# Third-party JavaScript library

This directory contains third-party JavaScript libraries required for HTML report rendering. These libraries have been inlined into the generated HTML files for use in offline environments.

## Included libraries

1. **chart.js** (204KB) - used for chart rendering
- Version: 4.5.1
- Source: https://cdn.jsdelivr.net/npm/chart.js

2. **chartjs-chart-sankey.js** (10KB) - Sankey chart plug-in
- Version: 0.12.0
- Source: https://unpkg.com/chartjs-chart-sankey@0.12.0/dist/chartjs-chart-sankey.min.js

3. **html2canvas.min.js** (194KB) - HTML to Canvas tool
- Version: 1.4.1
- Source: https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js

4. **jspdf.umd.min.js** (356KB) - PDF export library
- Version: 2.5.1
- Source: https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js

5. **mathjax.js** (1.1MB) - Mathematical formula rendering engine
- Version: 3.2.2
- Source: https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js

## Function description

The HTML renderer (`html_renderer.py`) will automatically load these library files from this directory and inline them into the generated HTML. This has the following advantages:

- ✅ Available in offline environment - no internet connection is required to display reports properly
- ✅ Fast loading speed - no reliance on external CDN
- ✅ High stability - not affected by CDN service interruptions
- ✅ Version fixed - ensures functional consistency

## Backup mechanism

If the library file fails to load (such as the file does not exist or a read error occurs), the renderer will automatically fall back to using a CDN link to ensure normal operation under any circumstances.

## Update library files

To update library files, please:

1. Download the latest version from the corresponding CDN
2. Replace the corresponding files in this directory
3. Update the version information in this README file

## Notes

- The total size is approximately 1.86MB, which will increase the size of the generated HTML file
- For simple reports that do not require charts and mathematical formulas, these libraries will still be included
- If you need to reduce file size, consider using lighter weight alternatives
