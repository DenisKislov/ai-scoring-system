"""Text adapters for benchmark and threshold calibration JSON documents."""

def vacancy_text_of(item: dict) -> str:
    body = []
    if item.get("responsibilities"):
        body.append(f"Обязанности: {item['responsibilities']}")
    if item.get("requirements"):
        body.append(f"Требования: {item['requirements']}")
    if body:
        return "\n\n".join([item.get("vacancy") or ""] + body).strip()
    return item.get("raw_text") or item.get("vacancy") or ""


def resume_text_of(item: dict) -> str:
    parts = []
    if item.get("career_goal"):
        parts.append(f"Цель: {item['career_goal']}")
    if item.get("key_strengths"):
        parts.append(f"Ключевые навыки и сильные стороны: {item['key_strengths']}")
    positions = item.get("previously_held_positions") or []
    if positions:
        exp_text = "\n".join(
            f"- {p.get('position', '')} в {p.get('company', '')} "
            f"({p.get('period', '')}): {p.get('responsibilities', '')}"
            for p in positions
        )
        parts.append(f"Опыт работы:\n{exp_text}")
    return "\n\n".join(p for p in parts if p).strip() or item.get("raw_text") or ""

