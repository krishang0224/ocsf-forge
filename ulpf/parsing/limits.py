"""Optional record budgets for interactive document ingestion."""


class InputLimitError(ValueError):
    pass


def check_event_limit(count: int, maximum: int | None) -> None:
    if maximum is not None:
        if maximum <= 0:
            raise ValueError("max_events must be positive")
        if count > maximum:
            raise InputLimitError(f"Input exceeds the {maximum:,}-event limit. Split it on complete record boundaries.")
