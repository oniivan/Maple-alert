from __future__ import annotations

from detectors.dead_player import detect_dead_player
from detectors.minimap_red import detect_minimap_red, locate_minimap_content_rect
from detectors.minimap_title import detect_free_market_title

__all__ = [
    "detect_dead_player",
    "detect_free_market_title",
    "detect_minimap_red",
    "locate_minimap_content_rect",
]
