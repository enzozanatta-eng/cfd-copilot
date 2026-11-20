"""Ghia, Ghia & Shin (1982) lid-driven cavity benchmark.

u-velocity along the vertical centreline (x = 0.5) of the unit cavity.
Reference: J. Comput. Phys. 48, 387-411, Table I.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Y = np.array([
    1.0000, 0.9766, 0.9688, 0.9609, 0.9531, 0.8516, 0.7344, 0.6172, 0.5000,
    0.4531, 0.2813, 0.1719, 0.1016, 0.0703, 0.0625, 0.0547, 0.0000,
])

U = {
    100: np.array([
        1.00000, 0.84123, 0.78871, 0.73722, 0.68717, 0.23151, 0.00332, -0.13641,
        -0.20581, -0.21090, -0.15662, -0.10150, -0.06434, -0.04775, -0.04192,
        -0.03717, 0.00000,
    ]),
    400: np.array([
        1.00000, 0.75837, 0.68439, 0.61756, 0.55892, 0.29093, 0.16256, 0.02135,
        -0.11477, -0.17119, -0.32726, -0.24299, -0.14612, -0.10338, -0.09266,
        -0.08186, 0.00000,
    ]),
    1000: np.array([
        1.00000, 0.65928, 0.57492, 0.51117, 0.46604, 0.33304, 0.18719, 0.05702,
        -0.06080, -0.10648, -0.27805, -0.38289, -0.29730, -0.22220, -0.20196,
        -0.18109, 0.00000,
    ]),
}


def available(reynolds: float) -> bool:
    return any(abs(reynolds - re) < 1e-9 for re in U)


@dataclass
class Comparison:
    reynolds: int
    rms_error: float
    max_error: float
    y_ref: np.ndarray
    u_ref: np.ndarray


def compare(reynolds: float, y_sim: np.ndarray, u_sim: np.ndarray) -> Comparison:
    """Interpolate the simulated profile at the benchmark points and compare."""
    re = int(round(reynolds))
    if re not in U:
        raise KeyError(f"no Ghia data for Re = {reynolds:g} (have {sorted(U)})")
    order = np.argsort(y_sim)
    u_at_ref = np.interp(Y, np.asarray(y_sim)[order], np.asarray(u_sim)[order])
    err = u_at_ref - U[re]
    return Comparison(
        reynolds=re,
        rms_error=float(np.sqrt(np.mean(err**2))),
        max_error=float(np.max(np.abs(err))),
        y_ref=Y,
        u_ref=U[re],
    )
