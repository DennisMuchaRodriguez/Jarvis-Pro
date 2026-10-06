"""YouTube, búsquedas en Google y páginas web."""
from __future__ import annotations

import re
import webbrowser
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from jarvis.skills.registry import registry


def first_youtube_video(query: str) -> str | None:
    """Devuelve el ID del primer video de la búsqueda en YouTube (o None)."""
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es"})
    html = urlopen(request, timeout=8).read().decode("utf-8", "ignore")
    match = re.search(r'"videoId":"([\w-]{11})"', html)
    return match.group(1) if match else None


@registry.tool(
    name="play_youtube",
    quick=True,
    description="Busca en YouTube y reproduce el primer video (canciones, tutoriales, trailers, etc.).",
    parameters={"query": {"type": "string", "description": "Qué buscar en YouTube."}},
)
def play_youtube(query: str) -> str:
    try:
        video_id = first_youtube_video(query)
    except OSError:
        video_id = None
    if video_id:
        webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")
        return f"Reproduciendo {query} en YouTube."
    webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
    return f"Abrí la búsqueda de {query} en YouTube; elija el video que prefiera."


@registry.tool(
    name="search_google",
    quick=True,
    description="Abre una búsqueda de Google en el navegador para que el usuario vea los resultados.",
    parameters={"query": {"type": "string", "description": "Texto a buscar."}},
)
def search_google(query: str) -> str:
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    return f"Buscando {query} en Google."


@registry.tool(
    name="open_website",
    quick=True,
    description="Abre una página web en el navegador.",
    parameters={"url": {"type": "string", "description": "Dirección, por ejemplo 'github.com'."}},
)
def open_website(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return "Página abierta."
