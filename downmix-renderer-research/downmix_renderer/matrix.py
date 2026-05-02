from __future__ import annotations

import numpy as np

# Sharur matrix from reference/renderer_app_original.py.
# Do not edit these coefficients without explicit user approval.
MATRIX_LITERAL = (
    (1.0, 0.0),
    (0.0, 1.0),
    (0.7071, 0.7071),
    (2.2646, 2.2646),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (0.0, 1.0),
)

MATRIX = np.array(MATRIX_LITERAL, dtype=np.float32)

