"""chartwright-synthdata: synthetic clinical documents + pixel-accurate ground truth."""

from chartwright_synthdata.degrade import Degradation, degrade
from chartwright_synthdata.generator import GeneratedDocument, generate_prior_auth
from chartwright_synthdata.values import SyntheticValues, make_values

__all__ = [
    "Degradation",
    "GeneratedDocument",
    "SyntheticValues",
    "degrade",
    "generate_prior_auth",
    "make_values",
]

__version__ = "0.1.0"
