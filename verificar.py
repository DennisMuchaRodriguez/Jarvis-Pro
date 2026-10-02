"""Revisa que todo esté listo para Jarvis y te dice qué falta.

    python verificar.py

No gasta dinero: para comprobar tu clave solo consulta la información del modelo.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
ROOT = Path(__file__).resolve().parent
problems = 0


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def bad(msg: str, fix: str) -> None:
    global problems
    problems += 1
    print(f"  [X]  {msg}\n       -> {fix}")


def warn(msg: str) -> None:
    print(f"  [!]  {msg}")


def check_python() -> None:
    print("\n1. Python")
    v = sys.version_info
    if (3, 10) <= v[:2] <= (3, 13):
        ok(f"Python {v.major}.{v.minor} ({sys.executable})")
    else:
        bad(f"Python {v.major}.{v.minor} no es compatible con todas las librerías de audio",
            "Instala Python 3.12 desde python.org y vuelve a ejecutar instalar.bat")
    if ".venv" not in sys.executable:
        warn("No estás usando el entorno .venv. En VS Code: Ctrl+Shift+P > 'Python: Select Interpreter' > .venv")


def check_packages() -> bool:
    print("\n2. Librerías")
    packages = {
        "anthropic": "anthropic", "dotenv": "python-dotenv", "numpy": "numpy",
        "sounddevice": "sounddevice", "speech_recognition": "SpeechRecognition", "pyaudio": "PyAudio",
        "edge_tts": "edge-tts", "pygame": "pygame", "pyttsx3": "pyttsx3",
        "pyautogui": "pyautogui", "pyperclip": "pyperclip", "psutil": "psutil",
    }
    missing = []
    for module, pip_name in packages.items():
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(pip_name)
    if missing:
        bad(f"Faltan: {', '.join(missing)}", "Ejecuta instalar.bat (o: pip install -r requirements.txt)")
    else:
        ok("Todas las librerías están instaladas")
    return "anthropic" not in missing and "python-dotenv" not in missing


def check_api_key() -> None:
    print("\n3. Clave de la API de Claude (.env)")
    if not (ROOT / ".env").exists():
        bad("No existe el archivo .env", "Copia .env.example como .env (instalar.bat lo hace por ti)")
        return
    from jarvis.config import load_settings

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or key.endswith("..."):
        bad("ANTHROPIC_API_KEY está vacía", "Pega tu clave de https://platform.claude.com en el archivo .env")
        return
    import anthropic

    model = load_settings().model
    try:
        anthropic.Anthropic().models.retrieve(model)
        ok(f"La clave funciona y el modelo {model} está disponible")
    except anthropic.AuthenticationError:
        bad("La clave no es válida", "Crea una nueva en platform.claude.com > API Keys y pégala completa")
    except anthropic.NotFoundError:
        bad(f"El modelo {model} no está disponible para tu cuenta", "Revisa JARVIS_MODEL en .env")
    except anthropic.APIConnectionError:
        bad("No hay conexión con la API", "Revisa tu internet o firewall")
    except anthropic.APIStatusError as exc:
        bad(f"La API respondió con error {exc.status_code}", "Revisa que tu cuenta tenga créditos (Billing)")


def check_data() -> None:
    print("\n4. Tus datos (carpeta data/)")
    for name in ("apps.json", "projects.json", "contacts.json"):
        try:
            data = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            bad(f"{name} tiene un error de formato (línea {exc.lineno})",
                "Revisa comas y comillas; en las rutas usa doble barra: C:\\\\Users\\\\...")
            continue
        entries = {k: v for k, v in data.items() if not k.startswith("_")}
        ok(f"{name}: {len(entries)} elementos")
        if name == "projects.json":
            for key, project in entries.items():
                if not Path(project.get("path", "")).exists():
                    warn(f"Proyecto '{key}': la carpeta no existe ({project.get('path')}). Pon la ruta real.")
        if name == "contacts.json":
            for key, contact in entries.items():
                if contact.get("phone", "").endswith("0000000000"):
                    warn(f"Contacto '{key}': todavía tiene el número de ejemplo.")


def check_tools() -> None:
    print("\n5. Programas externos")
    from jarvis.config import load_settings

    if shutil.which("code"):
        ok("Comando 'code' de VS Code disponible (para abrir proyectos)")
    else:
        warn("No encuentro el comando 'code'. Reinstala VS Code marcando 'Agregar a PATH' y reinicia VS Code.")
    unity = load_settings().unity_editor_path
    if unity and Path(unity).exists():
        ok("Editor de Unity encontrado")
    else:
        warn("UNITY_EDITOR_PATH en .env no existe. Búscalo en Unity Hub > Installs > (engranaje) > Show in Explorer")


def check_microphone() -> None:
    print("\n6. Micrófono")
    try:
        import sounddevice as sd
    except ImportError:
        warn("Se revisará cuando instales las librerías.")
        return
    try:
        device = sd.query_devices(kind="input")
        ok(f"Micrófono predeterminado: {device['name']}")
    except Exception as exc:
        bad(f"No pude acceder al micrófono ({exc})",
            "Conecta un micrófono y en Windows: Configuración > Privacidad > Micrófono > permitir apps de escritorio")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    print("Verificando la instalación de Jarvis...")
    check_python()
    if check_packages():
        check_api_key()
        check_data()
        check_tools()
    check_microphone()
    print()
    if problems:
        print(f"Hay {problems} problema(s) por resolver (marcados con [X]).")
    else:
        print("Todo listo. Prueba primero:  python main.py --texto")
