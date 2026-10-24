"""AI prompts live as Markdown next to this file: edit them to change what the model is asked, no Python needed."""
from pathlib import Path


def load(name):
    """str.format template from <name>.md: {placeholders} are filled in by code, literal braces are doubled ({{ }})."""
    return (Path(__file__).parent / f"{name}.md").read_text().rstrip()
