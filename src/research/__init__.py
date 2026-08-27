"""Evidence retrieval and optional AI synthesis for investment research."""

from .config import ResearchConfig
from .news import NewsItem, NewsResult, NewsService
from .ai import AIResearchResult, AIResearchService

__all__ = [
    "AIResearchResult",
    "AIResearchService",
    "NewsItem",
    "NewsResult",
    "NewsService",
    "ResearchConfig",
]
