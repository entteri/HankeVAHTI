"""Yhteinen Gemini-yhteys AI-soveltuvuusarviolle ja hakemustekstin muotoilulle. Ei tietokantakirjoituksia."""

import logging

import httpx
from google import genai
from google.genai import errors, types

from app.core import config

logger = logging.getLogger(__name__)

class GeminiError(Exception):
    """Käyttäjälle sellaisenaan näytettävä suomenkielinen virhe."""


def configuration_error() -> str | None:
    missing = []
    if not config.GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not config.GEMINI_MODEL:
        missing.append("GEMINI_MODEL")
    if missing:
        return (
            "Gemini ei ole käytössä. Lisää " + " ja ".join(missing)
            + " paikalliseen .env-tiedostoon ja käynnistä sovellus uudelleen."
        )
    return None


def generate_gemini_text(instructions: str, contents: str, *, json_schema: dict | None = None) -> str:
    """Lähetä työohje ja aineisto erillään; jaa virheenkäsittely kaikkien toimintojen kesken."""
    if message := configuration_error():
        raise GeminiError(message)
    try:
        # Client luodaan vasta pyynnöstä. Sulje HTTP-yhteydet myös virhetilanteessa.
        with genai.Client(
            api_key=config.GEMINI_API_KEY,
            vertexai=False,
            http_options=types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1)),
        ) as client:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=instructions,
                    max_output_tokens=4096,
                    response_mime_type="application/json" if json_schema is not None else None,
                    response_json_schema=json_schema,
                ),
            )
            candidates = getattr(response, "candidates", None)
            if candidates and candidates[0].finish_reason not in (None, types.FinishReason.STOP):
                raise GeminiError("Gemini ei saanut vastausta valmiiksi tai esti vastauksen. Lyhennä pyyntöä ja yritä uudelleen.")
            answer = response.text
        if not answer or not answer.strip():
            raise GeminiError("Gemini ei palauttanut tekstivastausta. Muotoile kysymys uudelleen ja yritä uudestaan.")
        return answer.strip()
    except GeminiError:
        raise
    except errors.APIError as exc:
        if exc.code == 429:
            message = "Geminin käyttöraja tai pyyntötiheys ylittyi. Odota hetki ja tarkista tarvittaessa API-kiintiösi."
        elif exc.code == 403 and "your project has been denied access" in (exc.message or "").casefold():
            message = (
                "Google on estänyt tämän projektin Gemini API -käytön (403). "
                "Tarkista API-avaimeen liittyvän projektin ilmoitukset Google Cloud Consolessa "
                "sekä AI Studion Projects- ja Billing-sivuilla. "
                "Jos syy ei selviä, ota yhteyttä Googlen tukeen."
            )
        elif exc.code in (401, 403):
            message = "Gemini ei hyväksynyt käyttöoikeutta. Tarkista API-avain ja mallin käyttöoikeus."
        elif exc.code == 404:
            message = "Gemini-mallia ei löytynyt. Tarkista GEMINI_MODEL ja mallin saatavuus."
        else:
            message = "Gemini-palvelun API-virhe. Yritä myöhemmin uudelleen ja tarkista tarvittaessa mallin asetukset."
        raise GeminiError(message) from None
    except (httpx.TimeoutException, TimeoutError):
        raise GeminiError("Geminin vastaus aikakatkaistiin. Yritä hetken kuluttua uudelleen.") from None
    except (httpx.RequestError, ConnectionError):
        raise GeminiError("Geminiin ei saatu verkkoyhteyttä. Tarkista yhteys ja yritä uudelleen.") from None
    except Exception as exc:
        # Älä lokita SDK:n virhetekstiä, pyyntöä tai avainta.
        logger.warning("Gemini-pyyntö epäonnistui (%s)", type(exc).__name__)
        raise GeminiError("Geminin pyyntö epäonnistui. Tarkista asetukset ja yritä uudelleen.") from None
