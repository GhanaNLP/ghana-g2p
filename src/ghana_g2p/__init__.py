"""ghana-g2p — grapheme-to-phoneme conversion for Ghanaian languages."""
from ghana_g2p.core import (
    GhanaG2P,
    Result,
    UnknownLanguage,
    g2p,
    languages,
    resolve,
)

__version__ = "0.1.0"
__all__ = ["GhanaG2P", "Result", "UnknownLanguage", "g2p", "languages", "resolve"]
