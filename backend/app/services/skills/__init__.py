"""Investigation skills for the Primary and Secondary SOC agents."""

from app.services.skills.otx_enrichment import enrich_iocs
from app.services.skills.attack_mapping import map_attack_techniques
from app.services.skills.log_correlation import correlate_logs
from app.services.skills.behavioral_deviation import detect_deviation

__all__ = [
    "enrich_iocs",
    "map_attack_techniques",
    "correlate_logs",
    "detect_deviation",
]
