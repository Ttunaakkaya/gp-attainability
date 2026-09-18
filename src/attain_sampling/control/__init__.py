"""Independent motion controllers; not an ECC 2025 equation reproduction."""

from attain_sampling.control.qp import QPResult, QPSettings, solve_tracking_qp

__all__ = ["QPResult", "QPSettings", "solve_tracking_qp"]
