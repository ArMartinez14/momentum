import unicodedata
from firebase_admin import firestore
from datetime import datetime, timedelta

def aplicar_progresion(valor_inicial, incremento, operacion):
    try:
        if operacion == "suma":
            return str(float(valor_inicial) + incremento)
        elif operacion == "resta":
            return str(float(valor_inicial) - incremento)
        elif operacion == "multiplicacion":
            return str(float(valor_inicial) * incremento)
        elif operacion == "division":
            return str(float(valor_inicial) / incremento)
        else:
            return valor_inicial
    except:
        return valor_inicial

def normalizar_texto(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')


def actualizar_progresiones_individual(nombre, correo, ejercicio, circuito, bloque, fecha_actual_lunes, dia_numero, peso_alcanzado):
    db = firestore.client()

    # Normalización
    correo_id = correo.replace("@", "_").replace(".", "_").lower()
    ejercicio_id = ejercicio.lower().replace(" ", "_")
    circuito_id = circuito.lower().replace(" ", "_") if circuito else ""
    bloque_id = bloque.lower().replace(" ", "_")
    dia_id = str(dia_numero)

    fecha_dt = datetime.strptime(fecha_actual_lunes, "%Y-%m-%d")
    fecha_actual_normal = fecha_dt.strftime("%Y_%m_%d")
    fecha_siguiente_normal = (fecha_dt + timedelta(weeks=1)).strftime("%Y_%m_%d")

    # Documentos
    doc_id_actual = f"{correo_id}_{fecha_actual_normal}_{dia_id}_{circuito_id}_{ejercicio_id}"
    doc_id_siguiente = f"{correo_id}_{fecha_siguiente_normal}_{dia_id}_{circuito_id}_{ejercicio_id}"

    doc_actual = db.collection("rutinas").document(doc_id_actual).get()
    if not doc_actual.exists:
        return

    try:
        peso_planificado = float(doc_actual.to_dict().get("peso", 0))
        diferencia = round(peso_alcanzado - peso_planificado, 1)
    except:
        return

    if diferencia == 0:
        return

    doc_siguiente_ref = db.collection("rutinas").document(doc_id_siguiente)
    doc_siguiente = doc_siguiente_ref.get()
    if not doc_siguiente.exists:
        return

    try:
        datos = doc_siguiente.to_dict()
        peso_original = float(datos.get("peso", 0))
        nuevo_peso = round(peso_original + diferencia, 1)
        doc_siguiente_ref.update({"peso": nuevo_peso})
    except:
        pass