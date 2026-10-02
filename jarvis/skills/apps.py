"""Abrir y cerrar programas y juegos. La lista vive en data/apps.json."""
from __future__ import annotations

from jarvis.skills._helpers import IS_WINDOWS, find_entry, load_data, normalize, open_target
from jarvis.skills.registry import registry

APPS = load_data("apps.json")
_KNOWN = ", ".join(APPS) or "(ninguno configurado)"


@registry.tool(
    name="open_app",
    description=(
        "Abre un programa o juego del PC. Programas y juegos configurados: "
        f"{_KNOWN}. Si piden algo que no está en la lista, intenta igualmente con el "
        "nombre del ejecutable (por ejemplo 'notepad', 'mspaint')."
    ),
    parameters={"name": {"type": "string", "description": "Nombre del programa o juego."}},
)
def open_app(name: str) -> str:
    match = find_entry(name, APPS)
    if match:
        key, entry = match
        open_target(entry["target"], entry.get("args"))
        return f"Abriendo {key}."
    open_target(name)
    return f"'{name}' no estaba configurado; lo intenté abrir directamente."


@registry.tool(
    name="close_app",
    description=f"Cierra un programa o juego abierto. Configurados: {_KNOWN}.",
    parameters={"name": {"type": "string", "description": "Nombre del programa o juego."}},
)
def close_app(name: str) -> str:
    import psutil

    match = find_entry(name, APPS)
    process_name = match[1].get("process", name) if match else name
    target = normalize(process_name)
    if not target.endswith(".exe") and IS_WINDOWS:
        target += ".exe"

    closed = 0
    for proc in psutil.process_iter(["name"]):
        if normalize(proc.info["name"] or "") == target:
            try:
                proc.terminate()
                closed += 1
            except psutil.Error:
                pass
    if closed:
        return f"Cerré {closed} proceso(s) de {process_name}."
    return f"No encontré ningún proceso abierto llamado {process_name}."
