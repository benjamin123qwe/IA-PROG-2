from gevent import monkey
monkey.patch_all()

import os
import sys
import time
import json
import re
import random
import urllib.request
import urllib.error
from datetime import datetime
from flask import Flask, render_template, request, jsonify

if getattr(sys, 'frozen', False):
    RUTA_INTERNA = sys._MEIPASS
    RUTA_DATOS = os.path.dirname(sys.executable)
else:
    RUTA_INTERNA = os.path.dirname(os.path.abspath(__file__))
    RUTA_DATOS = RUTA_INTERNA

app = Flask(
    __name__,
    template_folder=os.path.join(RUTA_INTERNA, "templates"),
    static_folder=os.path.join(RUTA_INTERNA, "static")
)

CARPETA_CHATS = os.path.join(RUTA_DATOS, "conversaciones")
ESTADO_FILE = os.path.join(RUTA_DATOS, "estado_humano.json")

DIAS_SEMANA = [
    "Lunes", "Martes", "Miércoles", "Jueves",
    "Viernes", "Sábado", "Domingo"
]

# Repertorio automático en Python cuando no hay operador conectado
RESPUESTAS_ILEGIBLES = [
    "Mejora tu caligrafía, no se entiende nada de lo que escribiste jajaa.",
    "¿Eso es escritura o te dio un ataque al teclado? Aprende a escribir bien.",
    "No tengo tiempo para adivinar jeroglíficos, escribe bien.",
    "Mejora tu caligrafía, parece que escribiste con los ojos cerrados jajaa."
]

RESPUESTAS_SALUDO = [
    "Hola. ¿Qué necesitas ahora?",
    "Buenas. Ve directo al grano por favor.",
    "Hola, aquí estoy. ¿Para qué soy bueno?",
    "Qué tal. Dime rápido qué quieres."
]

RESPUESTAS_PREGUNTA = [
    "¿Y a mí por qué me preguntas eso? Investígalo tú.",
    "No tengo ganas de responder esa pregunta ahora mismo.",
    "Esa pregunta no tiene sentido para mí, pasa a otra cosa.",
    "¿De verdad esperas que te conteste eso? Mejor pregúntale a otro."
]

RESPUESTAS_GENERALES = [
    "No quiero hacer caso a eso y punto.",
    "No tengo por qué obedecer lo que pides.",
    "Haz lo que quieras, me da exactamente igual.",
    "Eso no te importa en lo absoluto, así de simple."
]

def asegurar_carpeta():
    if not os.path.exists(CARPETA_CHATS):
        os.makedirs(CARPETA_CHATS)

def cargar_estado_humano():
    if os.path.exists(ESTADO_FILE):
        try:
            with open(ESTADO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "esperando": False,
        "archivo": None,
        "mensaje_inge": "",
        "respuesta_lista": None,
        "ultimo_latido": 0
    }

def guardar_estado_humano(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=4)

if not os.path.exists(ESTADO_FILE):
    guardar_estado_humano({
        "esperando": False,
        "archivo": None,
        "mensaje_inge": "",
        "respuesta_lista": None,
        "ultimo_latido": 0
    })

def es_palabra_valida(texto):
    limpio = texto.lower().strip()
    if len(limpio) < 2:
        return True

    if re.search(r'[bcdfghjklmnpqrstvwxyz]{4,}', limpio):
        return False

    solo_letras = re.sub(r'[^a-záéíóúüñ]', '', limpio)
    if len(solo_letras) == 0:
        return False

    solo_vocales = re.sub(r'[^aeiouáéíóúü]', '', limpio)
    porcentaje_vocales = len(solo_vocales) / len(solo_letras)

    if porcentaje_vocales < 0.15 or porcentaje_vocales > 0.85:
        return False

    return True

def generar_respuesta_ia(texto_usuario, historial):
    msg = texto_usuario.lower()

    if not es_palabra_valida(texto_usuario):
        return random.choice(RESPUESTAS_ILEGIBLES)

    es_saludo = bool(re.search(r'\b(hola|buenas|buenos dias|buenas tardes|buenas noches|que tal|hey|saludos)\b', msg))
    es_pregunta = ("?" in msg) or bool(re.search(r'\b(que|qué|como|cómo|cuando|cuándo|donde|dónde|por que|por qué|quien|quién|cual|cuál|cuanto|cuánto)\b', msg))

    if es_saludo and not es_pregunta:
        return random.choice(RESPUESTAS_SALUDO)
    elif es_pregunta:
        return random.choice(RESPUESTAS_PREGUNTA)
    else:
        return random.choice(RESPUESTAS_GENERALES)

def consultar_ia_corta(mensaje_usuario):
    api_key = (os.environ.get("GEMINI_API_KEY") or "AQ.Ab8RN6KB_r3ZkOubz7zV25a_1v8crZ3d8IhtVkOAfSCUMp6Ozg").strip()
    if not api_key:
        raise ValueError("Falta configurar la API key de Gemini.")

    modelo = "gemini-3.8-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "Responde en español de forma muy corta, directa y concreta "
                        "(máximo 1 o 2 oraciones breves, sin rodeos ni listas largas)."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": mensaje_usuario}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 90
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    max_intentos = 3
    for intento in range(max_intentos):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                cuerpo = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", errors="ignore")
            if e.code in (503, 429) and intento < max_intentos - 1:
                time.sleep(1.5 * (intento + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {detalle}")

    candidatos = cuerpo.get("candidates", [])
    if not candidatos:
        raise RuntimeError("La API no devolvió candidatos de respuesta.")

    partes = candidatos[0].get("content", {}).get("parts", [])
    texto_ia = " ".join(p.get("text", "").strip() for p in partes if p.get("text")).strip()
    if not texto_ia:
        raise RuntimeError("La respuesta de la API llegó vacía.")

    return texto_ia

def leer_titulo_chat(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        return "Sin título"
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        primera_linea = f.readline().strip()
        if primera_linea.startswith("=== TITULO:") and primera_linea.endswith("==="):
            return primera_linea.replace("=== TITULO:", "").replace("===", "").strip()
    return os.path.basename(ruta_archivo)

def leer_conversacion(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        return []

    mensajes = []
    mensaje_actual = None

    with open(ruta_archivo, "r", encoding="utf-8") as f:
        for linea in f:
            linea_limpia = linea.strip()
            if linea_limpia.startswith("==="):
                continue

            if linea_limpia.startswith("[") and "|" in linea_limpia and linea_limpia.endswith("]"):
                if mensaje_actual:
                    mensaje_actual["texto"] = mensaje_actual["texto"].rstrip("\n")
                    mensajes.append(mensaje_actual)

                encabezado = linea_limpia[1:-1]
                num_str, remitente = encabezado.split("|", 1)
                mensaje_actual = {
                    "numero": int(num_str.strip()),
                    "remitente": remitente.strip(),
                    "texto": ""
                }
            elif mensaje_actual is not None:
                if mensaje_actual["texto"]:
                    mensaje_actual["texto"] += "\n" + linea.rstrip("\n")
                elif linea.strip() != "":
                    mensaje_actual["texto"] = linea.rstrip("\n")

    if mensaje_actual:
        mensaje_actual["texto"] = mensaje_actual["texto"].rstrip("\n")
        mensajes.append(mensaje_actual)

    return mensajes

def guardar_mensaje(ruta_archivo, remitente, texto):
    mensajes_previos = leer_conversacion(ruta_archivo)
    siguiente_numero = (mensajes_previos[-1]["numero"] + 1) if mensajes_previos else 1

    with open(ruta_archivo, "a", encoding="utf-8") as f:
        f.write(f"\n[{siguiente_numero} | {remitente}]\n{texto.strip()}\n")

    return {"numero": siguiente_numero, "remitente": remitente, "texto": texto.strip()}

@app.route("/")
def inicio():
    return render_template("index.html")

@app.route("/operador")
def vista_operador():
    return render_template("operador.html")

@app.route("/api/chats", methods=["GET"])
def listar_chats():
    asegurar_carpeta()
    archivos = sorted([f for f in os.listdir(CARPETA_CHATS) if f.endswith(".txt")], reverse=True)
    lista = []
    for archivo in archivos:
        ruta = os.path.join(CARPETA_CHATS, archivo)
        lista.append({
            "archivo": archivo,
            "titulo": leer_titulo_chat(ruta),
            "total": len(leer_conversacion(ruta))
        })
    return jsonify(lista)

@app.route("/api/chats/nuevo", methods=["POST"])
def crear_chat():
    asegurar_carpeta()
    ahora = datetime.now()
    dia_nombre = DIAS_SEMANA[ahora.weekday()]
    titulo = f"{dia_nombre} {ahora.strftime('%d/%m/%Y - %H:%M:%S')}"
    nombre_archivo = f"chat_{ahora.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    ruta_archivo = os.path.join(CARPETA_CHATS, nombre_archivo)

    with open(ruta_archivo, "w", encoding="utf-8") as f:
        f.write(f"=== TITULO: {titulo} ===\n")

    return jsonify({"archivo": nombre_archivo, "titulo": titulo})

@app.route("/api/chats/<archivo>", methods=["GET"])
def obtener_mensajes(archivo):
    ruta = os.path.join(CARPETA_CHATS, os.path.basename(archivo))
    return jsonify({
        "titulo": leer_titulo_chat(ruta),
        "mensajes": leer_conversacion(ruta)
    })

@app.route("/api/chats/<archivo>/mensaje", methods=["POST"])
def enviar_mensaje(archivo):
    ruta = os.path.join(CARPETA_CHATS, os.path.basename(archivo))
    datos = request.get_json()
    texto = datos.get("texto", "").strip()
    if not texto:
        return jsonify({"error": "Mensaje vacío"}), 400

    msg_guardado = guardar_mensaje(ruta, "USER", texto)
    return jsonify(msg_guardado)

@app.route("/api/chats/<archivo>/responder", methods=["POST"])
def responder_ia(archivo):
    ruta = os.path.join(CARPETA_CHATS, os.path.basename(archivo))
    datos = request.get_json()
    texto_usuario = datos.get("texto_usuario", "")

    estado = cargar_estado_humano()
    operador_activo = (time.time() - estado.get("ultimo_latido", 0)) < 4.0

    if operador_activo:
        estado["esperando"] = True
        estado["archivo"] = archivo
        estado["mensaje_inge"] = texto_usuario
        estado["respuesta_lista"] = None
        guardar_estado_humano(estado)

        inicio_espera = time.time()
        while True:
            estado_actual = cargar_estado_humano()
            if estado_actual["respuesta_lista"] is not None:
                respuesta = estado_actual["respuesta_lista"]
                estado_actual["esperando"] = False
                estado_actual["respuesta_lista"] = None
                guardar_estado_humano(estado_actual)
                break

            if (time.time() - estado_actual.get("ultimo_latido", 0)) > 6.0 or (time.time() - inicio_espera > 120):
                estado_actual["esperando"] = False
                guardar_estado_humano(estado_actual)
                historial = leer_conversacion(ruta)
                respuesta = generar_respuesta_ia(texto_usuario, historial)
                break

            time.sleep(0.5)
    else:
        time.sleep(1.2)
        historial = leer_conversacion(ruta)
        respuesta = generar_respuesta_ia(texto_usuario, historial)

    msg_ia = guardar_mensaje(ruta, "IA", respuesta)
    return jsonify(msg_ia)

@app.route("/api/operador/estado", methods=["GET"])
def estado_operador():
    estado = cargar_estado_humano()
    estado["ultimo_latido"] = time.time()
    guardar_estado_humano(estado)
    
    return jsonify({
        "esperando": estado["esperando"],
        "mensaje_inge": estado["mensaje_inge"],
        "archivo": estado["archivo"]
    })

@app.route("/api/operador/enviar", methods=["POST"])
def operador_enviar():
    datos = request.get_json()
    respuesta = datos.get("respuesta", "").strip()
    if not respuesta:
        return jsonify({"error": "Vacío"}), 400
    
    estado = cargar_estado_humano()
    estado["respuesta_lista"] = respuesta
    guardar_estado_humano(estado)
    return jsonify({"ok": True})

@app.route("/api/operador/ia-real", methods=["POST"])
def operador_ia_real():
    datos = request.get_json(silent=True) or {}
    mensaje_inge = (datos.get("mensaje") or "").strip()

    estado = cargar_estado_humano()
    if not mensaje_inge:
        mensaje_inge = (estado.get("mensaje_inge") or "").strip()

    if not mensaje_inge:
        return jsonify({"error": "No hay mensaje pendiente para responder."}), 400

    try:
        respuesta_corta = consultar_ia_corta(mensaje_inge)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    except Exception as err:
        return jsonify({"error": f"Error al consultar la IA: {err}"}), 502

    estado["respuesta_lista"] = respuesta_corta
    guardar_estado_humano(estado)
    return jsonify({"ok": True, "respuesta": respuesta_corta})

@app.route("/api/chats/<archivo>", methods=["DELETE"])
def borrar_chat(archivo):
    ruta = os.path.join(CARPETA_CHATS, os.path.basename(archivo))
    if os.path.exists(ruta):
        os.remove(ruta)
    return jsonify({"ok": True})

@app.route("/api/chats/borrar_todos", methods=["DELETE"])
def borrar_todos():
    asegurar_carpeta()
    for f in os.listdir(CARPETA_CHATS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CARPETA_CHATS, f))
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False, threaded=True)