"""Entry point for the CiteVahti Claude Desktop Extension (.mcpb).

Claude Desktop launches this with `python3 server/main.py --root <ledger dir>`.
Dependencies (citevahti + mcp + pydantic + httpx + transitive) are vendored into
`server/lib/` at build time, so this prepends that directory to the import path and
then hands off to the normal stdio MCP server entry point. No global install needed.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "lib")
if os.path.isdir(_LIB) and _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from citevahti.agent.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
