"""Pydantic schema models for the ``.citevahti/`` state layer.

These implement the approved reference design plus the binding additions and the
ten sign-off patches. They are the implementation target; do not redesign.
"""

from .common import (
    GroupLibrary,
    ItemRef,
    LibrarySelector,
    PassageRef,
    Provenance,
    ToolError,
    ToolResult,
)
from .config import (
    AIProvenanceConfig,
    Config,
    Endpoints,
    PubMedConfig,
    RateLimit,
    RatingConfig,
    SchemeSpec,
    WritebackConfig,
    ZoteroConfig,
)
from .evidence_map import (
    Attachment,
    EvidenceMap,
    Link,
    Node,
    ReverseIndexEntry,
)
from .frame import Domain, Frame, Level, Outcome, Pico, Scheme, Study
from .rating import (
    AccessLogEntry,
    Adjudication,
    AIProvenance,
    AIRating,
    Blinding,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)

__all__ = [
    # common
    "LibrarySelector",
    "GroupLibrary",
    "ItemRef",
    "PassageRef",
    "Provenance",
    "ToolError",
    "ToolResult",
    # config
    "Config",
    "Endpoints",
    "ZoteroConfig",
    "PubMedConfig",
    "RateLimit",
    "RatingConfig",
    "SchemeSpec",
    "AIProvenanceConfig",
    "WritebackConfig",
    # frame
    "Frame",
    "Scheme",
    "Level",
    "Domain",
    "Outcome",
    "Study",
    "Pico",
    # rating
    "RatingRecord",
    "Subject",
    "HumanRating",
    "AIRating",
    "AIProvenance",
    "Comparison",
    "Adjudication",
    "Blinding",
    "AccessLogEntry",
    # evidence map
    "EvidenceMap",
    "Node",
    "Link",
    "Attachment",
    "ReverseIndexEntry",
]
