"""Read-only Zotero local-API access (step 2).

The local ``/api/`` is treated as read-only / GET-only. All reads respect the
``library`` selector. When the API is unreachable the service degrades honestly
to a ``ToolResult`` failure with remediation -- it never fabricates data.
"""

from .connect import ZoteroConnectError, ZoteroConnectService, new_key_url
from .library import LibrarySelectorError, bases_for, coerce_library, base_path
from .oauth import ZoteroOAuth, ZoteroOAuthError, load_client_credentials
from .read import ZoteroService

__all__ = [
    "ZoteroService",
    "LibrarySelectorError",
    "base_path",
    "bases_for",
    "coerce_library",
    "ZoteroConnectService",
    "ZoteroConnectError",
    "new_key_url",
    "ZoteroOAuth",
    "ZoteroOAuthError",
    "load_client_credentials",
]
