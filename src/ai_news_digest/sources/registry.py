"""Active source registry. Add or replace sources here; the pipeline reads this list.

URLs were verified live during PLAN v2 (see PLAN.md §4).
"""

from __future__ import annotations

from .arxiv import ArxivSource
from .base import Source
from .rss import RSSSource

DEFAULT_SOURCES: list[Source] = [
    RSSSource("OpenAI Blog",          "https://openai.com/blog/rss.xml"),
    RSSSource("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    RSSSource("Google Research Blog", "https://research.google/blog/rss/"),
    RSSSource("Google Blog (AI)",     "https://blog.google/technology/ai/rss/"),
    RSSSource("Microsoft Research",   "https://www.microsoft.com/en-us/research/feed/"),
    RSSSource("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml"),
    RSSSource("Stability AI News",    "https://stability.ai/news-updates?format=rss"),
    RSSSource("NVIDIA Blogs",         "https://blogs.nvidia.com/feed/"),
    RSSSource("BAIR",                 "https://bair.berkeley.edu/blog/feed.xml"),
    ArxivSource("cs.AI"),
    ArxivSource("cs.CL"),
    ArxivSource("cs.LG"),
]
