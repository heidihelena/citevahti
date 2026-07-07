"""The public tools facade — a pure re-export surface (ADR-0010, decomposition complete).

Every tool is implemented in a group module under ``tools/`` and re-exported here so
``from citevahti.tools import X`` (and ``engine.X`` attribute access from the CLI, panel,
and agent surface) keeps working unchanged — the 101-name public surface is frozen by
tests/test_tools_public_api_stable.py.

Group map (read-only -> ledger-write -> write-privileged):
``zotero_read`` / ``search`` / ``reports`` / ``manuscript`` / ``lexical`` (read-only) ·
``claims`` / ``rating`` / ``support`` / ``intake`` / ``corpus`` / ``warehouse`` (audited
ledger) · ``exports`` (local files) · ``settings`` (config) · ``writeback`` — the ONE
write-privileged module that can mutate an external Zotero library (ADR-0010 §5c).
Shared factories live in ``_common``; group modules never import back into this facade.
"""

from __future__ import annotations



# Shared factory helpers re-exported for tests/back-compat; the group modules import
# them from ._common directly (the neutral module — no cycle back into this facade).
from ._common import _intake_service, _open_store, _pubmed_provider  # noqa: F401
from .writeback import (  # noqa: F401
    annotation_add,
    assessment_tag_mirror,
    collection_add_item,
    commit_decision,
    connect_zotero,
    get_transaction,
    intake_push,
    item_add,
    list_transactions,
    note_add,
    tag_add,
    tag_remove,
    undo_transaction,
    zotero_new_key_url,
    zotero_oauth_finish,
    zotero_oauth_start,
)
from .settings import (  # noqa: F401
    ai_config_get,
    ai_config_set,
    ai_local_models,
    bib_sync,
    getting_started,
    onboard,
)
from .exports import (  # noqa: F401
    agreement_report,
    cite_export,
    cite_export_manuscript,
    evidence_export,
    export_report_docx,
    export_review_packet,
)
from .warehouse import (  # noqa: F401
    aggregate_ratings,
    atlas_contribution_preview,
    atlas_revoke,
    prisma_ledger,
    warehouse_configure,
    warehouse_emit,
    warehouse_export,
    warehouse_purge,
    warehouse_status,
)
from .corpus import (  # noqa: F401
    corpus_diff,
    map_bootstrap,
    snapshot,
    surveillance_refresh,
)
from .intake import (  # noqa: F401
    backfill_candidate_dois,
    import_results,
    literature_search,
    recheck_library,
    retraction_scan,
    scan_licenses,
    scan_retractions,
)
from .lexical import (  # noqa: F401
    claim_check,
    claim_lexical_check,
    extract,
)
from .support import (  # noqa: F401
    decide,
    get_support_rating,
    list_decisions,
    support_adjudicate,
    support_commit_human,
    support_compare,
    support_panel,
    support_run_ai,
    support_start,
)
from .rating import (  # noqa: F401
    assess,
    rating_adjudicate,
    rating_commit_human,
    rating_compare,
    rating_run_ai,
    rating_start,
)
from .claims import (  # noqa: F401
    accept_revision,
    add_claim,
    claim_bond_status,
    claim_mark_untestable,
    link_candidates,
    list_candidates,
    list_claims,
    propose_revision,
    reject_revision,
    unlink_candidate,
)
from .manuscript import (  # noqa: F401
    chat,
    check_paragraph,
    claim_tests_prompt,
    import_manuscript_docx,
    run_manuscript_tests,
    topic_screen_prompt,
)
from .reports import (  # noqa: F401
    claim_report,
    draft_context,
    evidence_map,
    methods_statement,
    model_advisor,
    triage,
)
from .search import (  # noqa: F401
    check_update,
    openalex_search,
    resolve_dois,
    resolve_dois_by_title,
    semanticscholar_search,
)
from .zotero_read import (  # noqa: F401
    cite,
    pandoc_status,
    zot_attachments,
    zot_collections,
    zot_item,
    zot_search,
    zotero_evidence,
    zotero_locate,
)
