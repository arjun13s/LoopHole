"""Test session config.

Gate (Design-Y) scenarios are OPT-IN in production (scenarios._include_gate) —
training and the audit eval never use them, so the served taskset is audit-only.
The test suite still exercises gate functionality, so enable it here (set before
any test imports env, which builds env._SCENARIOS once at import). Production
leaves LOOP_AUDITOR_GATE unset -> audit-only.
"""

import os

os.environ.setdefault("LOOP_AUDITOR_GATE", "1")
