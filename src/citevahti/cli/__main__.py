"""Keep ``python -m citevahti.cli`` working after the package conversion (ADR-0010 PR 3b).

As a single module, ``python -m citevahti.cli`` executed the file directly; a package
needs this ``__main__`` shim. The CI workflow's CLI smoke step invokes exactly this form.
"""

import sys

from . import main

sys.exit(main())
