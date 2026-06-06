"""assess: record a human-chosen controlled rating value (step 7).

Never computes, suggests, or pre-fills the value. Creates an assessment typed
attachment only after the human commits. May start the blinded dual-rating flow.
"""

from .service import AssessmentService

__all__ = ["AssessmentService"]
