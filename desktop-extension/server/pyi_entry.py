"""PyInstaller entry point — frozen into a standalone `citevahti-mcp` executable.

Unlike server/main.py (which adds a vendored lib/ to sys.path for the python-type
bundle), the binary build has citevahti + mcp + deps compiled in, so this just calls
the stdio MCP server's main(). Args (e.g. --root) are passed straight through.
"""
from citevahti.agent.mcp_server import main

if __name__ == "__main__":
    raise SystemExit(main())
