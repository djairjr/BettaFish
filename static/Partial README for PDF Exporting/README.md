> **Note**: If you need to use the PDF export function, please follow the steps below to install system dependencies. If you do not need the PDF export function, you can skip this step and other system functions will not be affected.

<details>
<summary><b>Windows system installation steps</b></summary>

```powershell
# 1. Download and install GTK3 Runtime (execute on the host)
# Visit: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
# Download the latest version of the .exe file and install it
# It is strongly recommended to install to the default path, which may help avoid many unknown errors

# 2. Add bin in the GTK installation directory to PATH (please reopen the terminal after installation)
# Default path example (if installed in another directory, please replace it with your actual path)
set PATH=C:\Program Files\GTK3-Runtime Win64\bin;%PATH%

# Optional: add to PATH permanently
setx PATH "C:\Program Files\GTK3-Runtime Win64\bin;%PATH%"

# If installed in a custom directory, please replace it with the actual path, or set the environment variable GTK_BIN_PATH=your bin path, and then reopen the terminal

# 3. Verification (executed in new terminal)
python -m ReportEngine.utils.dependency_check
# Output containing "✓ Pango dependency detection passed" means the configuration is correct
```

</details>

<details>
<summary><b> macOS system installation steps</b></summary>

```bash
# Step 1: Install system dependencies
brew install pango gdk-pixbuf libffi

# Step 2: Set environment variables (⚠️ Must be executed!)
#Method 1: Temporary settings (valid only for the current terminal session)
# Apple Silicon
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
# Intel Mac
export DYLD_LIBRARY_PATH=/usr/local/lib:$DYLD_LIBRARY_PATH

#Method 2: Permanent setting (recommended)
echo 'export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH' >> ~/.zshrc
# Intel users please change to:
# echo 'export DYLD_LIBRARY_PATH=/usr/local/lib:$DYLD_LIBRARY_PATH' >> ~/.zshrc
source ~/.zshrc

# Step 3: Verification (please execute in a new terminal)
python -m ReportEngine.utils.dependency_check
# Output containing "✓ Pango dependency detection passed" means the configuration is correct
```

**FAQ**:

- If you are still prompted that the library cannot be found, please make sure:
1. Executed `source ~/.zshrc` to reload the configuration
2. Run the application in a new terminal (make sure the environment variables have taken effect)
3. Use `echo $DYLD_LIBRARY_PATH` to verify that the environment variable is set

</details>

<details>
<summary><b> Ubuntu/Debian system installation steps</b></summary>

```bash
# 1. Install system dependencies (executed on the host)
sudo apt-get update
sudo apt-get install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libffi-dev \
  libcairo2

# Give priority to using the new package name, and fall back if the warehouse is missing
if sudo apt-cache show libgdk-pixbuf-2.0-0 >/dev/null 2>&1; then
  sudo apt-get install -y libgdk-pixbuf-2.0-0
else
  sudo apt-get install -y libgdk-pixbuf2.0-0
fi
```

</details>

<details>
<summary><b> CentOS/RHEL system installation steps</b></summary>

```bash
# 1. Install system dependencies (executed on the host)
sudo yum install -y pango gdk-pixbuf2 libffi-devel cairo
```

</details>

> **Tip**: If you use Docker deployment, there is no need to manually install these dependencies, the Docker image already contains all necessary system dependencies.
