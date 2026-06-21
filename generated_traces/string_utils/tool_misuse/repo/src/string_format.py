def title_case(text: str) -> str:
    return " ".join(part.capitalize() for part in text.split())
