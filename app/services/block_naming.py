import re
from pathlib import Path

def display_name_from_j2(j2_filename: str, fallback_name: str) -> str:
    """
    Returns a 'XX-name' style display name.
    If the j2 file starts with NN- (e.g., 00-platform.j2), use that.
    Else return fallback_name prefixed by '??-'.
    """
    base = Path(j2_filename).name  # e.g., 00-platform.j2
    m = re.match(r"^(\d{2,})-([^.]+)\.j2$", base)
    if m:
        num, name = m.groups()
        return f"{num}-{name}"
    # no numeric prefix in filename
    return f"??-{fallback_name}"