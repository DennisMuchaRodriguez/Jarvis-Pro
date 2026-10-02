"""Abrir proyectos de programación (VS Code, Unity o carpeta). Lista en data/projects.json."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jarvis.config import load_settings
from jarvis.skills._helpers import find_entry, load_data, open_target
from jarvis.skills.registry import registry

PROJECTS = load_data("projects.json")
_KNOWN = ", ".join(PROJECTS) or "(ninguno configurado)"


@registry.tool(
    name="open_project",
    description=f"Abre uno de los proyectos del usuario en su editor. Proyectos: {_KNOWN}.",
    parameters={"name": {"type": "string", "description": "Nombre del proyecto."}},
)
def open_project(name: str) -> str:
    match = find_entry(name, PROJECTS)
    if not match:
        return f"No tengo un proyecto llamado '{name}'. Proyectos configurados: {_KNOWN}."
    key, project = match
    path = project["path"]
    if not Path(path).exists():
        return f"La carpeta del proyecto {key} no existe: {path}. Revisa data/projects.json."

    kind = project.get("type", "folder")
    if kind == "unity":
        editor = project.get("editor") or load_settings().unity_editor_path
        if not editor or not Path(editor).exists():
            return "No encuentro el editor de Unity. Configura UNITY_EDITOR_PATH en .env."
        subprocess.Popen([editor, "-projectPath", path])
        return f"Abriendo el proyecto {key} en Unity. Tardará un poco en cargar."
    if kind == "vscode":
        code = shutil.which("code")
        if not code:
            return "No encuentro el comando 'code' de VS Code en el PATH."
        subprocess.Popen([code, path])
        return f"Abriendo {key} en Visual Studio Code."
    open_target(path)
    return f"Abriendo la carpeta de {key}."
