"""PyInstaller entry point for the CiteVahti desktop app.

Frozen into a windowed, double-clickable bundle (CiteVahti.app / CiteVahti.exe) by
build-app.sh. It just calls the desktop launcher, which brings the loopback panel up and
shows it in the OS-native webview — no browser, no Python required on the user's machine.
"""

import sys

from citevahti.desktop import main

if __name__ == "__main__":
    sys.exit(main())
