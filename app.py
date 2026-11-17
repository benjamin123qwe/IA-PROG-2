import os
import sys
import time
import socket
import json
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
        "respuesta_lista": None
    }

def guardar_estado_humano(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=4)

# Crear el archivo json de estado si no existe
if not os.path.exists(ESTADO_FILE):
    guardar_estado_humano({
        "esperando": False,
        "archivo": None,
        "mensaje_inge": "",
        "respuesta_lista": None
    })

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

def generar_respuesta_ia(texto_usuario, historial):
    return "nose"

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
    modo = datos.get("modo", "ia")

    if modo == "humano":
        estado = cargar_estado_humano()
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

            if time.time() - inicio_espera > 120:
                estado_actual["esperando"] = False
                guardar_estado_humano(estado_actual)
                return jsonify({"error": "Tiempo agotado"}), 408
            
            time.sleep(0.5)
    else:
        historial = leer_conversacion(ruta)
        respuesta = generar_respuesta_ia(texto_usuario, historial)

    msg_ia = guardar_mensaje(ruta, "IA", respuesta)
    return jsonify(msg_ia)

@app.route("/api/operador/estado", methods=["GET"])
def estado_operador():
    estado = cargar_estado_humano()
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