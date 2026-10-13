# Easy installers

These installers create a private virtual environment, install Graphify and add a graphical folder-picker launcher.

## Windows

Download and double-click `ChatGPTGraphifyInstaller.exe` from the project’s GitHub Actions artifact or release.

The installer checks for Python 3.12.7. If Python is missing, it downloads and installs Python for the current Windows user, then installs Graphify and creates a **ChatGPT Graphify** desktop shortcut. No terminal or command prompt is required.

The repository also keeps `install-windows.bat` as a developer fallback for local source checkouts.

## macOS

Double-click `install-macos.command`. It installs **ChatGPT Graphify.app** in `~/Applications` and opens it.

Both installers require Python 3.9+ to already be installed. They do not require users to type terminal commands.
