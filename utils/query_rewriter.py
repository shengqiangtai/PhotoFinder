from __future__ import annotations

import re
from dataclasses import dataclass


VISUAL_TERM_MAP = {
    "日落": "sunset",
    "夕阳": "sunset",
    "海边": "beach",
    "沙滩": "beach",
    "森林": "forest",
    "树林": "forest",
    "城市": "city",
    "夜景": "night city",
    "雪山": "snow mountain",
    "草地": "grass field",
    "狗": "dog",
    "小狗": "dog",
    "猫": "cat",
    "人": "person",
    "人物": "person",
    "汽车": "car",
    "车": "car",
    "建筑": "building",
    "花": "flower",
    "树": "tree",
    "天空": "sky",
    "奔跑": "running",
    "站着": "standing",
    "坐着": "sitting",
    "红色": "red",
    "蓝色": "blue",
    "明亮": "bright",
    "黑白": "black and white",
}


@dataclass
class RewrittenQuery:
    original_query: str
    rewritten_query: str
    was_rewritten: bool


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def rewrite_query_for_clip(query: str) -> RewrittenQuery:
    normalized = " ".join(query.split())
    if not contains_cjk(normalized):
        return RewrittenQuery(
            original_query=query,
            rewritten_query=normalized,
            was_rewritten=False,
        )

    rewritten_terms: list[str] = []
    for source, target in VISUAL_TERM_MAP.items():
        if source in normalized and target not in rewritten_terms:
            rewritten_terms.append(target)

    rewritten_query = " ".join(rewritten_terms) if rewritten_terms else normalized
    return RewrittenQuery(
        original_query=query,
        rewritten_query=rewritten_query,
        was_rewritten=rewritten_query != normalized,
    )
