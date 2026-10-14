"""Read editable AI documents from the project, independently of the working directory."""

from pathlib import Path

from app.core.config import PROJECT_ROOT


class DocumentError(Exception):
    """A local AI document cannot be used."""


def read_ai_document(filename: str, *, root: Path = PROJECT_ROOT) -> str:
    path = root / filename
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DocumentError(f"Tiedosto {filename} puuttuu projektikansiosta.") from exc
    except (OSError, UnicodeError) as exc:
        raise DocumentError(f"Tiedostoa {filename} ei voitu lukea. Tarkista käyttöoikeudet ja UTF-8-tallennus.") from exc
    if not content.strip():
        raise DocumentError(f"Tiedosto {filename} on tyhjä.")
    return content
