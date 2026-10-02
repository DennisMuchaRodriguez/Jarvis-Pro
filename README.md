# J.A.R.V.I.S. Pro 🤖

Asistente por voz al estilo de Iron Man, hecho en Python: **se despierta con dos aplausos**, te escucha, te
responde con voz y controla tu PC (abre programas y juegos, pone videos de YouTube, envía mensajes de WhatsApp,
abre tus proyectos de VS Code o Unity, controla el volumen y la música, etc.).

---

## 1. La idea en una imagen

```
            🎤 Micrófono                                   🔊 Altavoces
                 │                                              ▲
     ┌───────────▼────────────┐                     ┌───────────┴───────────┐
     │  OÍDO (jarvis/audio)   │                     │  VOZ (jarvis/audio)   │
     │  • clap_detector  👏👏 │                     │  • text_to_speech     │
     │  • speech_to_text  🗣️→📝│                     │    📝→🗣️ (edge-tts)    │
     └───────────┬────────────┘                     └───────────▲───────────┘
                 │ texto: "pon lofi en YouTube"                 │ "Enseguida, señor."
     ┌───────────▼──────────────────────────────────────────────┴───────────┐
     │            NÚCLEO (jarvis/core/assistant.py)                          │
     │            dormido ⇄ despierto ⇄ conversando                          │
     └───────────┬──────────────────────────────────────────────▲───────────┘
                 │ orden + historial                            │ texto a decir
     ┌───────────▼──────────────────────────────────────────────┴───────────┐
     │            CEREBRO (jarvis/brain) → Claude API                        │
     │            entiende la orden y decide qué herramienta usar            │
     └───────────┬──────────────────────────────────────────────▲───────────┘
                 │ play_youtube(query="lofi")                   │ "Reproduciendo..."
     ┌───────────▼──────────────────────────────────────────────┴───────────┐
     │            HABILIDADES (jarvis/skills) → tu PC                        │
     │   apps · web · projects · messaging · system · assistant              │
     └───────────────────────────────────────────────────────────────────────┘
```

**¿Por qué así?** La parte difícil de un Jarvis no es abrir programas (eso son 2 líneas de Python), sino
**entender lo que dices** de forma natural: "ponme algo para concentrarme", "abre mi juego de Unity",
"dile a mi mamá que llego tarde". Para eso usamos un modelo de lenguaje (Claude) con *tool use*: le damos una
lista de funciones de Python y él decide cuál llamar y con qué argumentos. Así no tienes que escribir
cientos de `if "youtube" in texto: ...`.

---

## 2. Estructura del proyecto

```
Jarvis-Pro/
├── main.py                      ← punto de entrada (python main.py)
├── .env.example                 ← plantilla de configuración (cópiala como .env)
├── requirements.txt
├── data/                        ← TUS datos, edítalos sin tocar código
│   ├── apps.json                ← programas y juegos (nombre → ejecutable / steam://...)
│   ├── projects.json            ← tus proyectos (VS Code / Unity)
│   └── contacts.json            ← contactos de WhatsApp
├── jarvis/
│   ├── config.py                ← lee .env y lo expone como `Settings`
│   ├── audio/
│   │   ├── clap_detector.py     ← 👏👏 detecta el doble aplauso (numpy + sounddevice)
│   │   ├── speech_to_text.py    ← 🗣️→📝 voz a texto (Google o Whisper local)
│   │   ├── text_to_speech.py    ← 📝→🗣️ texto a voz (edge-tts, respaldo pyttsx3)
│   │   └── console.py           ← teclado/consola para el modo --texto
│   ├── brain/
│   │   ├── prompts.py           ← personalidad de Jarvis (system prompt)
│   │   └── llm.py               ← ciclo de conversación con Claude + herramientas
│   ├── core/
│   │   └── assistant.py         ← máquina de estados: dormido → escuchando → pensando
│   └── skills/                  ← lo que Jarvis SABE HACER
│       ├── registry.py          ← decorador @registry.tool y ejecución segura
│       ├── _helpers.py          ← abrir cosas, buscar nombres parecidos
│       ├── apps.py              ← open_app, close_app
│       ├── web.py               ← play_youtube, search_google, open_website
│       ├── projects.py          ← open_project (VS Code / Unity / carpeta)
│       ├── messaging.py         ← send_whatsapp (pide confirmación)
│       ├── system.py            ← volumen, multimedia, dictado, captura, hora, apagar...
│       └── assistant.py         ← go_to_sleep
└── tests/                       ← pruebas automáticas (pytest), no usan micrófono ni API
```

---

## 3. Cómo funciona cada pieza

### 3.1 El aplauso 👏👏 (`jarvis/audio/clap_detector.py`)
Mientras Jarvis duerme, solo este módulo usa el micrófono, y **no envía nada a internet**. Lee el audio en
bloques de 20 ms y busca sonidos que sean:
1. **Mucho más fuertes** que el ruido de fondo (que se va midiendo solo), y
2. **Muy cortos** (< 150 ms). Una voz o una canción pueden ser fuertes, pero duran más → se descartan.

Si hay **dos** de esos sonidos separados entre 0.12 y 0.8 s → ¡despierta!
La lógica (`DoubleClapDetector`) está separada del micrófono (`ClapListener`) para poder probarla con audio
falso en `tests/test_clap_detector.py`.

### 3.2 El oído 🗣️→📝 (`speech_to_text.py`)
Usa la librería `SpeechRecognition`, que detecta cuándo empiezas y terminas de hablar. El audio se transcribe con:
- **google** (por defecto): gratis, muy bueno en español, necesita internet.
- **whisper**: corre en tu PC (sin internet) con `faster-whisper`. Mejor si tienes GPU.

### 3.3 El cerebro 🧠 (`jarvis/brain/llm.py`)
Este es el corazón. En cada orden:
1. Envía a Claude la personalidad, la lista de herramientas y la conversación.
2. Claude responde con texto ("Enseguida, señor") y/o pide usar herramientas
   (`play_youtube(query="lofi")`).
3. Ejecutamos esas herramientas en tu PC y le devolvemos el resultado.
4. Se repite hasta que Claude termina. Cada texto que escribe se dice en voz alta al momento.

Detalles importantes:
- **Memoria**: recuerda la conversación mientras está despierto ("ábrelo otra vez" funciona). Al dormirse, la olvida.
- **Búsqueda web**: puede buscar en internet para preguntas de actualidad (`JARVIS_WEB_SEARCH`).
- **Velocidad**: `JARVIS_EFFORT=low` hace que piense menos y responda más rápido, ideal para voz.
- **Caché de prompts**: la personalidad y las herramientas se cachean → peticiones más baratas.

### 3.4 La voz 📝→🗣️ (`text_to_speech.py`)
`edge-tts` usa las voces neuronales de Microsoft (gratis y muy naturales, ej. `es-MX-JorgeNeural`). Si no hay
internet, usa `pyttsx3` con las voces de Windows.

### 3.5 Las habilidades 🛠️ (`jarvis/skills/`)
Son funciones normales de Python con un decorador. Claude lee su `description` para saber cuándo usarlas.

| Habilidad | Qué hace | Ejemplo de orden |
|---|---|---|
| `open_app` / `close_app` | Abre/cierra programas y juegos de `apps.json` | "Abre Spotify", "cierra el Counter" |
| `play_youtube` | Reproduce el primer video de una búsqueda | "Pon música lofi en YouTube" |
| `search_google` / `open_website` | Búsquedas y páginas | "Busca cómo hacer un shader en Unity" |
| `open_project` | Abre proyectos en VS Code o Unity | "Abre mi juego de Unity" |
| `send_whatsapp` | Envía mensajes (**pide confirmación**) | "Dile a mi mamá que llego en 10 minutos" |
| `set_volume` / `media_control` | Volumen y música | "Sube el volumen", "siguiente canción" |
| `type_text` | Dicta texto donde esté el cursor | "Escribe: hola equipo, ya subí los cambios" |
| `take_screenshot`, `system_status`, `get_datetime`, `lock_pc` | Utilidades | "¿Cómo va la batería?" |
| `power` | Apagar / reiniciar (**pide confirmación**) | "Apaga el PC" |
| `go_to_sleep` | Vuelve a dormir | "Gracias Jarvis, descansa" |

### 3.6 El núcleo 🔁 (`jarvis/core/assistant.py`)
Una máquina de estados sencilla:
```
DORMIDO ──👏👏──▶ saluda ──▶ ESCUCHA ──frase──▶ PIENSA/ACTÚA ──▶ ESCUCHA ...
   ▲                            │ silencio 2 veces           │ "descansa"
   └────────────────────────────┴────────────────────────────┘
```
Las acciones delicadas (`confirm=` en el decorador) hacen que Jarvis pregunte en voz alta
"¿Envío a mamá el mensaje...?" y solo continúa si dices "sí".

---

## 4. Instalación (Windows)

1. Instala **Python 3.10 o superior** (marca "Add Python to PATH").
2. En una terminal, dentro de la carpeta del proyecto:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Consigue una clave de la API de Claude en <https://platform.claude.com> → *API Keys*.
4. Copia `.env.example` como `.env` y pon tu `ANTHROPIC_API_KEY` y tu nombre.
5. Edita `data/apps.json`, `data/projects.json` y `data/contacts.json` con tus programas, rutas y contactos.
   - Para juegos de Steam: clic derecho en el juego → *Propiedades* → el número de la URL de la tienda es el ID
     (`steam://rungameid/ID`).
   - Para cerrar programas, `process` es el nombre que ves en el Administrador de tareas → *Detalles*.

## 5. Uso

```bash
python main.py --texto          # 1º prueba escribiendo (sin micrófono): verifica el cerebro y las habilidades
python main.py --sin-aplausos   # 2º prueba la voz: despierta con Enter
python -m jarvis.audio.clap_detector   # 3º calibra los aplausos (mira el "pico" de tus aplausos)
python main.py                  # 4º ¡modo Iron Man completo!
```
Añade `--debug` para ver todo lo que pasa por dentro.

**Calibrar aplausos:** ejecuta el calibrador, aplaude y habla. Pon `JARVIS_CLAP_THRESHOLD` en `.env` un poco
por debajo del pico de tus aplausos y por encima del pico de tu voz.

## 6. Cómo añadir una habilidad nueva

Ejemplo: abrir la carpeta de Descargas. Crea `jarvis/skills/files.py`:

```python
from pathlib import Path
from jarvis.skills._helpers import open_target
from jarvis.skills.registry import registry

@registry.tool(
    name="open_downloads",
    description="Abre la carpeta de Descargas del usuario.",
)
def open_downloads() -> str:
    open_target(str(Path.home() / "Downloads"))
    return "Carpeta de descargas abierta."
```

y añádelo al import de `load_skills()` en `jarvis/skills/__init__.py`. ¡Listo! Ya puedes decir
"Jarvis, abre mis descargas". Con parámetros:

```python
@registry.tool(
    name="open_folder",
    description="Abre una carpeta del usuario.",
    parameters={"name": {"type": "string", "enum": ["Descargas", "Documentos", "Escritorio"]}},
)
def open_folder(name: str) -> str: ...
```

## 7. Pruebas

```bash
pytest
```
Las pruebas no usan el micrófono ni la API (usan audio sintético y un cliente falso), así que son gratis.

## 8. Costos y privacidad
- Mientras duerme (esperando aplausos) **no se envía nada** a internet.
- Cada orden es una petición a la API de Claude (se paga por uso; con `effort=low` y caché, cada orden suele
  costar centavos de dólar o menos). Revisa tu consumo en la consola de Anthropic.
- El reconocimiento `google` envía el audio de tus frases a Google; usa `whisper` si prefieres que sea local.

## 9. Ideas para seguir (roadmap)
- **Palabra de activación "Jarvis"** además de los aplausos (con `openwakeword` o `pvporcupine`).
- **Respuestas en streaming**: empezar a hablar mientras Claude todavía escribe (menos espera).
- **Interfaz holográfica en Unity** 🎮: como ya sabes Unity, puedes hacer el HUD de Jarvis (el círculo azul
  que se anima cuando habla). Python enviaría el estado (`dormido`, `escuchando`, `hablando`) y el texto por
  WebSocket o UDP local, y Unity lo dibuja. El cerebro sigue en Python; Unity solo es la "cara".
- Más habilidades: Spotify (API oficial), Discord/Telegram (bots), recordatorios y alarmas, control de luces
  inteligentes, leer correos, controlar OBS para streaming.
- Ejecutar Jarvis al iniciar Windows (acceso directo en `shell:startup` con `pythonw main.py`).

## 10. Solución de problemas
| Problema | Solución |
|---|---|
| `pip install PyAudio` falla | Actualiza pip (`python -m pip install -U pip`) y usa Python 3.10–3.13, que tienen paquetes listos. |
| No detecta aplausos / se despierta solo | Calibra con `python -m jarvis.audio.clap_detector` y ajusta `JARVIS_CLAP_THRESHOLD`. |
| No entiende lo que digo | Revisa `JARVIS_LANGUAGE`, acércate al micrófono, o prueba `JARVIS_STT_ENGINE=whisper`. |
| WhatsApp no envía | Abre WhatsApp Desktop e inicia sesión antes; o usa `WHATSAPP_MODE=web`. |
| "clave no válida" | Revisa `ANTHROPIC_API_KEY` en `.env`. |
