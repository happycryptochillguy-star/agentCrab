"""Hierarchical category taxonomy on top of Polymarket's flat tag system.

Two-level hierarchy mapping our category paths to verified Gamma API tag_slug values.
Pure data + utility functions — no external calls.
"""

from __future__ import annotations

CATEGORIES: dict[str, dict] = {
    "politics": {
        "label": "Politics",
        "description": "US politics, global elections, geopolitics, economic policy",
        "tag_slugs": ["politics"],
        "subcategories": {
            "us": {
                "label": "US Politics",
                "tag_slugs": ["us-politics", "us-presidential-election", "congress"],
            },
            "trump": {
                "label": "Trump",
                "tag_slugs": ["trump", "trump-presidency", "trump-100-days"],
            },
            "elections": {
                "label": "Global Elections",
                "tag_slugs": ["global-elections", "elections", "world-elections"],
            },
            "geopolitics": {
                "label": "Geopolitics",
                "tag_slugs": ["geopolitics"],
                "subcategories": {
                    "middle_east": {
                        "label": "Middle East",
                        "tag_slugs": ["middle-east", "israel", "iran", "gaza"],
                    },
                    "ukraine": {
                        "label": "Ukraine / Russia",
                        "tag_slugs": ["ukraine"],
                    },
                    "china": {
                        "label": "China",
                        "tag_slugs": ["china"],
                    },
                },
            },
            "economy": {
                "label": "Economy & Policy",
                "tag_slugs": ["economy", "economic-policy"],
                "subcategories": {
                    "fed": {
                        "label": "Federal Reserve",
                        "tag_slugs": ["fed", "fed-rates"],
                    },
                    "commodities": {
                        "label": "Commodities",
                        "tag_slugs": ["commodities"],
                    },
                    "stocks": {
                        "label": "Stocks & Pre-Market",
                        "tag_slugs": ["pre-market"],
                    },
                },
            },
        },
    },
    "sports": {
        "label": "Sports",
        "description": "NBA, NFL, soccer, MMA, F1, and more",
        "tag_slugs": ["sports"],
        "subcategories": {
            "nba": {
                "label": "NBA / Basketball",
                "tag_slugs": ["nba", "basketball"],
            },
            "nfl": {
                "label": "NFL",
                "tag_slugs": ["nfl", "nfl-playoffs"],
            },
            "soccer": {
                "label": "Soccer",
                "tag_slugs": ["soccer"],
                "subcategories": {
                    "epl": {
                        "label": "English Premier League",
                        "tag_slugs": ["EPL", "premier-league"],
                    },
                    "ucl": {
                        "label": "Champions League",
                        "tag_slugs": ["ucl", "champions-league"],
                    },
                    "la_liga": {
                        "label": "La Liga",
                        "tag_slugs": ["la-liga"],
                    },
                    "ligue_1": {
                        "label": "Ligue 1",
                        "tag_slugs": ["ligue-1"],
                    },
                },
            },
            "mma": {
                "label": "MMA / Boxing",
                "tag_slugs": ["ufc", "boxing"],
            },
            "f1": {
                "label": "Formula 1",
                "tag_slugs": ["formula1", "f1"],
            },
            "mlb": {
                "label": "MLB",
                "tag_slugs": ["mlb"],
            },
            "tennis": {
                "label": "Tennis",
                "tag_slugs": ["tennis"],
            },
            "hockey": {
                "label": "Hockey / NHL",
                "tag_slugs": ["nhl", "hockey"],
            },
            "college": {
                "label": "College Sports",
                "tag_slugs": ["cfb", "ncaa", "college-football"],
            },
            "esports": {
                "label": "Esports",
                "tag_slugs": ["esports"],
            },
        },
    },
    "crypto": {
        "label": "Crypto",
        "description": "Cryptocurrency prices, airdrops, memecoins",
        "tag_slugs": ["crypto"],
        "subcategories": {
            "prices": {
                "label": "Crypto Prices",
                "tag_slugs": ["crypto-prices", "hit-price"],
            },
            "bitcoin": {
                "label": "Bitcoin",
                "tag_slugs": ["bitcoin"],
            },
            "ethereum": {
                "label": "Ethereum",
                "tag_slugs": ["ethereum"],
            },
            "solana": {
                "label": "Solana",
                "tag_slugs": ["solana"],
            },
            "airdrops": {
                "label": "Airdrops & Token Sales",
                "tag_slugs": ["airdrops", "token-sales"],
            },
            "memecoins": {
                "label": "Memecoins",
                "tag_slugs": ["memecoins"],
            },
        },
    },
    "pop_culture": {
        "label": "Pop Culture",
        "description": "Movies, music, celebrities, tweets, awards",
        "tag_slugs": ["pop-culture"],
        "subcategories": {
            "movies": {
                "label": "Movies & Entertainment",
                "tag_slugs": ["movies", "entertainment", "box-office"],
            },
            "music": {
                "label": "Music",
                "tag_slugs": ["music"],
            },
            "celebrities": {
                "label": "Celebrities",
                "tag_slugs": ["celebrities"],
            },
            "tweets": {
                "label": "Tweet Markets",
                "tag_slugs": ["tweets-markets", "elon-tweets"],
            },
            "awards": {
                "label": "Awards",
                "tag_slugs": ["awards"],
            },
        },
    },
    "tech": {
        "label": "Tech",
        "description": "AI, big tech, science",
        "tag_slugs": ["tech"],
        "subcategories": {
            "ai": {
                "label": "AI",
                "tag_slugs": ["ai", "openai", "deepseek", "grok"],
            },
            "big_tech": {
                "label": "Big Tech",
                "tag_slugs": ["big-tech"],
            },
            "science": {
                "label": "Science",
                "tag_slugs": ["science"],
            },
        },
    },
    "finance": {
        "label": "Finance",
        "description": "Financial markets, stocks, indices",
        "tag_slugs": ["finance"],
    },
    "world": {
        "label": "World / Breaking News",
        "description": "Global news and events not fitting other categories",
        "tag_slugs": ["world", "breaking-news"],
    },
}


def resolve_category(path: str) -> dict | None:
    """Walk the category tree with a dot-separated path.

    Examples:
        resolve_category("sports") → sports node
        resolve_category("sports.soccer.epl") → EPL node
        resolve_category("nonexistent") → None
    """
    parts = path.split(".")
    node = CATEGORIES.get(parts[0])
    if node is None:
        return None

    for part in parts[1:]:
        subs = node.get("subcategories")
        if not subs or part not in subs:
            return None
        node = subs[part]

    return node


def get_tag_slugs(path: str) -> list[str]:
    """Return all tag_slugs for a category path, including subcategory slugs.

    If path points to a node with subcategories, collects slugs from the node
    itself plus all direct children (one level deep) for broader coverage.
    """
    node = resolve_category(path)
    if node is None:
        return []

    slugs = list(node.get("tag_slugs", []))

    # Also include direct children's slugs for broader coverage
    subs = node.get("subcategories")
    if subs:
        for child in subs.values():
            slugs.extend(child.get("tag_slugs", []))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _build_node(key: str, node: dict) -> dict:
    """Build a single node for API response."""
    result: dict = {
        "id": key,
        "label": node.get("label", key),
    }
    if "description" in node:
        result["description"] = node["description"]

    subs = node.get("subcategories")
    if subs:
        result["subcategories"] = [
            _build_node(k, v) for k, v in subs.items()
        ]

    return result


def build_category_tree() -> list[dict]:
    """Flatten the taxonomy into a list suitable for API response."""
    return [_build_node(k, v) for k, v in CATEGORIES.items()]
