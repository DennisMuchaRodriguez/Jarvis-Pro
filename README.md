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
│   ├── contacts.json            ← contactos de WhatsApp
│   └── discord.json             ← amigos y canales de Discord
├── jarvis/
│   ├── config.py                ← lee .env y lo expone como `Settings`
│   ├── audio/
│   │   ├── clap_detector.py     ← 👏👏 detecta el doble aplauso (numpy + sounddevice)
│   │   ├── recorder.py          ← 🎙️ graba tu frase completa (detector de voz + ganancia)
│   │   ├── speech_to_text.py    ← 🗣️→📝 voz a texto (Google o Whisper local)
│   │   ├── text_to_speech.py    ← 📝→🗣️ texto a voz (edge-tts, respaldo pyttsx3)
│   │   └── console.py           ← teclado/consola para el modo --texto
│   ├── brain/
│   │   ├── prompts.py           ← personalidad de Jarvis (system prompt)
│   │   └── llm.py               ← ciclo de conversación con Claude + herramientas
│   ├── core/
│   │   ├── assistant.py         ← máquina de estados: dormido → escuchando → pensando
│   │   └── events.py            ← buzón donde los servicios dejan avisos para Jarvis
│   ├── services/                ← trabajan en segundo plano
│   │   ├── scheduler.py         ← ⏰ mensajes programados (jarvis_datos/programados.json)
│   │   └── notifications.py     ← 🔔 lee las notificaciones de Windows (mensajes recibidos)
│   └── skills/                  ← lo que Jarvis SABE HACER
│       ├── registry.py          ← decorador @registry.tool y ejecución segura
│       ├── _helpers.py          ← abrir cosas, buscar nombres parecidos
│       ├── apps.py              ← open_app, close_app
│       ├── web.py               ← play_youtube, search_google, open_website
│       ├── projects.py          ← open_project (VS Code / Unity / carpeta)
│       ├── messaging.py         ← send_whatsapp (pide confirmación)
│       ├── discord.py           ← send_discord, discord_voice (mute / ensordecer)
│       ├── scheduling.py        ← schedule_message, list/cancel_scheduled_message
│       ├── inbox.py             ← get_recent_messages
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

### 3.2 El oído 🗣️→📝 (`recorder.py` + `speech_to_text.py`)
Primero `recorder.py` graba tu frase **completa**:
- Suena un **bip**: ya puedes hablar.
- Mide 300 ms el ruido de tu cuarto y ajusta la ganancia: si el cuarto está en silencio, amplifica mucho
  (para voces lejanas); si hay ruido, poco (para no confundir el ruido con voz).
- Un **detector de voz** (webrtcvad, el de Google Meet) revisa cada trozo de 30 ms. Reconoce la voz humana por
  su forma, no solo por el volumen.
- Considera que terminaste tras **1.2 s de silencio** (`JARVIS_SILENCE_END`), así que las pausas normales
  ("pon en YouTube... eh... música para programar") no cortan la orden.
- Guarda 0.8 s de audio previo para no perder la primera sílaba, y sube el volumen de la grabación antes de
  transcribirla.

Después la frase se transcribe con:
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
- **Hora actual**: cada orden lleva la fecha y hora, así entiende "a las 9" o "en 20 minutos".

**Trucos de velocidad** (ver también § 5d):
- **Streaming**: Jarvis dice cada frase en cuanto Claude la escribe, sin esperar la respuesta completa.
- **Acciones rápidas**: las habilidades marcadas `quick=True` (abrir, reproducir, enviar...) anuncian su
  resultado ("Abriendo Spotify.") sin una segunda petición a Claude. Ahorra un viaje completo a la API.
- **Caché de prompts precalentado**: al despertar, prepara el caché en segundo plano mientras te saluda.
- **`JARVIS_EFFORT=low`** y la instrucción "responde sin deliberar" para que piense lo justo.

### 3.4 La voz 📝→🗣️ (`text_to_speech.py`)
`edge-tts` usa las voces neuronales de Microsoft (gratis y muy naturales, ej. `es-MX-JorgeNeural`). Si no hay
internet, usa `pyttsx3` con las voces de Windows.

Trabaja en segundo plano: un hilo genera el audio y otro lo reproduce, así la siguiente frase se prepara
mientras suena la anterior, y Jarvis ejecuta la orden mientras habla. Las frases ya dichas se guardan en una
carpeta temporal, así que los saludos y respuestas frecuentes suenan al instante.

### 3.5 Las habilidades 🛠️ (`jarvis/skills/`)
Son funciones normales de Python con un decorador. Claude lee su `description` para saber cuándo usarlas.

| Habilidad | Qué hace | Ejemplo de orden |
|---|---|---|
| `open_app` / `close_app` | Abre/cierra programas y juegos de `apps.json` | "Abre Spotify", "cierra el Counter" |
| `play_youtube` | Reproduce el primer video de una búsqueda | "Pon música lofi en YouTube" |
| `search_google` / `open_website` | Búsquedas y páginas | "Busca cómo hacer un shader en Unity" |
| `open_project` | Abre proyectos en VS Code o Unity | "Abre mi juego de Unity" |
| `send_whatsapp` | Envía mensajes (**pide confirmación**) | "Dile a mi mamá que llego en 10 minutos" |
| `send_discord` | Envía mensajes a amigos, grupos o canales de servidores (**pide confirmación**) | "Mándale a Carlos por Discord que ya me conecto", "escribe en el general del servidor: ¿quién juega?" |
| `discord_voice` | Te mutea o ensordece en Discord | "Mutéame", "ensordéceme" |
| `schedule_message` | Programa un mensaje de WhatsApp o Discord (**pide confirmación**) | "A las 9 mándale a mi mamá que ya salgo" |
| `list_scheduled_messages` / `cancel_scheduled_message` | Ver o cancelar programados | "¿Qué mensajes tengo programados?", "cancela el 2" |
| `get_recent_messages` | Te dice los mensajes que te llegaron | "¿Quién me escribió?" |
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

Los **servicios** (mensajes programados y avisos de mensajes) corren en hilos aparte, pero nunca hablan ni
tocan el teclado por su cuenta: dejan un aviso en `core/events.py` y el núcleo lo atiende cuando el micrófono
y los altavoces están libres (mientras duerme, o entre una orden y otra). Así Jarvis no habla encima de sí
mismo ni graba su propia voz como si fuera una orden.

---

## 4. Instalación paso a paso (Windows + VS Code)

1. **Confía en la carpeta**: en VS Code, pulsa *Manage* en la barra azul de "Restricted Mode" → *Trust*.
   (En modo restringido VS Code marca los acentos con recuadros y desactiva extensiones.)
2. **Instala Python 3.12** desde <https://www.python.org/downloads/> marcando *Add python.exe to PATH*.
   Evita 3.14: algunas librerías de audio aún no tienen versión para él.
3. **Instala la extensión "Python"** de Microsoft (VS Code te la sugiere al abrir el proyecto).
4. **Ejecuta el instalador**: menú *Terminal → New Terminal* y escribe `.\instalar.bat`.
   Crea el entorno `.venv`, instala todo, crea tu `.env` y ejecuta `verificar.py`.
5. **Selecciona el intérprete**: `Ctrl+Shift+P` → *Python: Select Interpreter* → el que dice `.venv`.
6. **Clave de API**: entra a <https://platform.claude.com>, crea tu cuenta, agrega créditos en *Billing*
   y crea una clave en *API Keys*. Pégala en `.env` → `ANTHROPIC_API_KEY=sk-ant-...` y guarda (`Ctrl+S`).
7. **Personaliza** `data/apps.json`, `data/projects.json`, `data/contacts.json`, `data/discord.json` y el resto de `.env`.
   - En los `.json`, las rutas llevan **doble barra**: `"C:\\Users\\Dennis\\Unity\\MiJuego"`. En `.env`, barra normal.
   - Juegos de Steam: clic derecho en el juego → *Propiedades* → *Actualizaciones*: ahí aparece el *ID de la aplicación*
     (`steam://rungameid/ID`).
   - Para cerrar programas, `process` es el nombre que ves en el Administrador de tareas → *Detalles*.
8. **Verifica**: `python verificar.py` hasta que no quede ningún `[X]`.

## 5. Uso

Pestaña *Run and Debug* (`Ctrl+Shift+D`): elige una opción en la lista de arriba y pulsa **F5**.

| Opción | Equivale a | Para qué |
|---|---|---|
| 1. Verificar instalación | `python verificar.py` | Revisa que todo esté listo |
| 2. Jarvis: modo texto | `python main.py --texto` | Le escribes; prueba el cerebro y las habilidades |
| 3. Jarvis: voz, despertar con Enter | `python main.py --sin-aplausos` | Prueba micrófono y voz |
| 3b. Probar micrófono | `python -m jarvis.audio.recorder` | Graba, muestra lo que entendió y guarda `prueba_microfono.wav` |
| 4. Calibrar aplausos | `python -m jarvis.audio.clap_detector` | Ajusta la sensibilidad |
| 5. Jarvis completo | `python main.py` | ¡Modo Iron Man! |

Añade `--debug` para ver todo lo que pasa por dentro.

**Calibrar aplausos:** ejecuta el calibrador, aplaude y habla. Pon `JARVIS_CLAP_THRESHOLD` en `.env` un poco
por debajo del pico de tus aplausos y por encima del pico de tu voz.

## 5b. Discord

**Enviar mensajes.** Cada destino de `data/discord.json` usa una de estas formas:

| Campo | Para qué | Cómo se envía |
|---|---|---|
| `link` | **Un canal concreto de un servidor** o un chat concreto | Abre ese canal en la app, pega el mensaje y lo envía desde tu cuenta. Es lo más exacto. En Discord: clic derecho sobre el canal → **Copiar enlace**. |
| `search` | Amigos y grupos | Usa el buscador `Ctrl+K` de Discord. Prefijos: `@usuario`, `#canal`. Desde tu cuenta. |
| `webhook` | Canales donde tengas permiso de gestionar webhooks | Sin abrir la app, 100% fiable, pero firmado "Jarvis". *Ajustes del servidor → Integraciones → Webhooks*. |

```json
"carlos":       { "aliases": ["carlitos"], "search": "@carlos_gamer" },
"general gamers": { "aliases": ["el general"], "link": "https://discord.com/channels/111.../222..." },
"chat del equipo": { "aliases": ["el equipo"], "link": "https://discord.com/channels/111.../333..." }
```
Si dices un destino que no está en el archivo, Jarvis lo busca con `Ctrl+K`. Con `link` y `search` necesitas la
app de Discord abierta con tu sesión, y **no tocar el teclado** esos segundos.

**Mutearte y ensordecerte.** Discord tiene `Ctrl+Shift+M` / `Ctrl+Shift+D`, pero solo funcionan con Discord al
frente (Jarvis lo traería al frente y te sacaría del juego). Mejor crea **atajos globales**:
1. Discord → ⚙️ Ajustes de usuario → **Atajos de teclado** → *Añadir un atajo*.
2. Acción **"Alternar silencio"** con `Ctrl+Shift+F9`, y otro **"Alternar ensordecer"** con `Ctrl+Shift+F10`.
3. En `.env`: `DISCORD_MUTE_HOTKEY=ctrl+shift+f9` y `DISCORD_DEAFEN_HOTKEY=ctrl+shift+f10`.

Son interruptores: "mutéame" otra vez te desmutea.

Usar tu cuenta con un "self-bot" (token de usuario) va contra las reglas de Discord y pueden banearte; por eso
Jarvis controla la app como lo harías tú.

## 5c. Mensajes programados y avisos de mensajes

**Programar:** *"Jarvis, a las 9 de la noche mándale a mi papá por WhatsApp que ya voy"*, *"mañana a las 8
escribe en el general del servidor: buenos días"*. Te pide confirmación y lo guarda en `jarvis_datos/` (no se
sube a GitHub). También: *"¿qué mensajes tengo programados?"*, *"cancela el mensaje 2"*.
- **Jarvis tiene que estar encendido** a esa hora (puede estar dormido). Si estaba apagado y el retraso es de
  menos de 2 horas, lo envía al encenderse; si es más, te avisa de que no pudo.
- Antes de enviarlo te avisa en voz alta, porque usará el teclado unos segundos.

**Avisos de mensajes recibidos:** cuando te llega un WhatsApp o un mensaje de Discord, Jarvis dice
*"Mensaje de Mamá por WhatsApp: ¿vienes a cenar?"*, esté dormido o despierto. También puedes preguntarle
*"¿quién me escribió?"*.
- Funciona leyendo las **notificaciones de Windows**, así que las apps deben tener las notificaciones activadas
  (en Windows y dentro de la app). Discord no notifica mientras lo tienes en primer plano, y el modo "No
  molestar" las silencia.
- Elige las apps con `JARVIS_NOTIFY_APPS` (por ejemplo `whatsapp,discord,telegram`) y si lee el texto o solo
  quién escribió con `JARVIS_NOTIFY_READ_TEXT`.

## 5d. Velocidad: qué la determina y cómo ajustarla

Tiempo de una orden ≈ **fin de tu frase** (`JARVIS_SILENCE_END`, 1.2 s) + **transcripción** (~0.5–1 s) +
**Claude** (lo que más pesa) + **voz** (~0.5 s, o nada si la frase ya está en caché).

| Ajuste en `.env` | Efecto |
|---|---|
| `JARVIS_MODEL=claude-sonnet-5-5` | Responde notablemente más rápido que Opus y cuesta la mitad; muy bueno para órdenes de voz. **Recomendado si buscas velocidad.** |
| `JARVIS_MODEL=claude-haiku-4-5` | El más rápido y barato, pero se equivoca más con órdenes complicadas. |
| `JARVIS_EFFORT=low` | Ya viene así: piensa lo justo. `medium` = más listo pero más lento. |
| `JARVIS_SILENCE_END=0.9` | Termina de escucharte antes. Bájalo solo si no haces pausas largas al hablar. |
| `JARVIS_WEB_SEARCH=false` | Quita la búsqueda web (ahorra un poco en cada petición). |

## 6. Cómo añadir una habilidad nueva

Ejemplo: abrir la carpeta de Descargas. Crea `jarvis/skills/files.py`:

```python
from pathlib import Path
from jarvis.skills._helpers import open_target
from jarvis.skills.registry import registry

@registry.tool(
    name="open_downloads",
    description="Abre la carpeta de Descargas del usuario.",
    quick=True,  # es una acción: Jarvis dice el resultado sin volver a preguntarle a Claude
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
- **Interfaz holográfica en Unity** 🎮: como ya sabes Unity, puedes hacer el HUD de Jarvis (el círculo azul
  que se anima cuando habla). Python enviaría el estado (`dormido`, `escuchando`, `hablando`) y el texto por
  WebSocket o UDP local, y Unity lo dibuja. El cerebro sigue en Python; Unity solo es la "cara".
- Más habilidades: Spotify (API oficial), Discord/Telegram (bots), recordatorios y alarmas, control de luces
  inteligentes, leer correos, controlar OBS para streaming.
- Ejecutar Jarvis al iniciar Windows (acceso directo en `shell:startup` con `pythonw main.py`).

## 10. Solución de problemas
| Problema | Solución |
|---|---|
| Me corta la orden | Sube `JARVIS_SILENCE_END` en `.env` (1.5 o 2). |
| No me oye de lejos | Prueba `JARVIS_VAD_MODE=0` y sube el micrófono en Windows: Configuración → Sistema → Sonido → tu micrófono → Volumen 100. En *Más opciones de sonido* → Grabación → Propiedades → Niveles, activa "Aumento del micrófono" si existe. |
| Usa el micrófono equivocado | `python verificar.py` lista los micrófonos; pon el número en `JARVIS_MIC_DEVICE`. |
| Graba ruido (ventilador, música) | Sube `JARVIS_VAD_MODE` a 2 o 3. |
| Discord escribe en el chat equivocado | Usa `link` (enlace del canal) o el nombre exacto con `@` en `search` dentro de `data/discord.json`. |
| Discord abre el canal pero no escribe el mensaje | Sube `DISCORD_OPEN_WAIT`; si sigue, usa `search` con `#canal` en lugar de `link`. |
| "Mutéame" no hace nada | Crea los atajos globales en Discord (§ 5b) iguales a los de `.env`. |
| No me avisa de mensajes | Activa las notificaciones de WhatsApp/Discord en Windows y en la app; desactiva "No molestar". `python verificar.py` revisa que se puedan leer. |
| No envió un mensaje programado | Jarvis debe estar encendido a esa hora; mira `jarvis_datos/programados.json`. |
| No detecta aplausos / se despierta solo | Calibra con `python -m jarvis.audio.clap_detector` y ajusta `JARVIS_CLAP_THRESHOLD`. |
| No entiende lo que digo | Revisa `JARVIS_LANGUAGE`, acércate al micrófono, o prueba `JARVIS_STT_ENGINE=whisper`. |
| WhatsApp no envía | Abre WhatsApp Desktop e inicia sesión antes; o usa `WHATSAPP_MODE=web`. |
| "clave no válida" | Revisa `ANTHROPIC_API_KEY` en `.env`. |
