import os
import sys
import time
import socket
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

DIAS_SEMANA = [
    "Lunes", "Martes", "Miércoles", "Jueves",
    "Viernes", "Sábado", "Domingo"
]

pendiente_humano = {
    "esperando": False,
    "archivo": None,
    "mensaje_inge": "",
    "respuesta_lista": None
}

def asegurar_carpeta():
    if not os.path.exists(CARPETA_CHATS):
        os.makedirs(CARPETA_CHATS)

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

def obtener_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

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
        pendiente_humano["esperando"] = True
        pendiente_humano["archivo"] = archivo
        pendiente_humano["mensaje_inge"] = texto_usuario
        pendiente_humano["respuesta_lista"] = None

        inicio_espera = time.time()
        while pendiente_humano["respuesta_lista"] is None:
            if time.time() - inicio_espera > 120:
                pendiente_humano["esperando"] = False
                return jsonify({"error": "Tiempo agotado"}), 408
            time.sleep(0.3)

        respuesta = pendiente_humano["respuesta_lista"]
        pendiente_humano["esperando"] = False
        pendiente_humano["respuesta_lista"] = None
    else:
        historial = leer_conversacion(ruta)
        respuesta = generar_respuesta_ia(texto_usuario, historial)

    msg_ia = guardar_mensaje(ruta, "IA", respuesta)
    return jsonify(msg_ia)

@app.route("/api/operador/estado", methods=["GET"])
def estado_operador():
    return jsonify({
        "esperando": pendiente_humano["esperando"],
        "mensaje_inge": pendiente_humano["mensaje_inge"],
        "archivo": pendiente_humano["archivo"]
    })

@app.route("/api/operador/enviar", methods=["POST"])
def operador_enviar():
    datos = request.get_json()
    respuesta = datos.get("respuesta", "").strip()
    if not respuesta:
        return jsonify({"error": "Vacío"}), 400
    pendiente_humano["respuesta_lista"] = respuesta
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
    print("=" * 55)
    print(f" Ventana 1 (PC):      http://localhost/?modo=ia")
    print(f" Ventana 2 (PC):      http://localhost/?modo=humano")
    print(f" Panel Celular:       http://192.168.0.14:80/operador")
    print("=" * 55)

    # 0.0.0.0 permite que responda a localhost desde la PC y a la IP desde el celular
    app.run(host="0.0.0.0", port=80, debug=False, threaded=True)