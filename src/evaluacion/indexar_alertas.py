#!/usr/bin/env python3
"""Carga en Elasticsearch las alertas OFFLINE de Isolation Forest (T5) y de las reglas (T6) sobre el lote, para verlas
en el dashboard de Kibana junto a los eventos (T8).

    python3 src/evaluacion/indexar_alertas.py

Índice: lab-alertas-offline (el rol lab_analyst solo puede escribir en lab-alertas*). @timestamp = fin de la ventana,
que es el primer momento en que la alerta podía emitirse. Cada alerta tiene un _id fijo
(<fuente>-<detector>-<sesión>-v<ventana>), así que volver a correr el script no duplica nada.
Las alertas de la prueba en vivo (T7) están aparte, en lab-alertas-AAAA.MM.DD, con lab.modo = "vivo" implícito.
Solo biblioteca estándar.
"""
import base64
import csv
import json
import os
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "src", "extraccion"))
from validar_ingesta import ES, leer_env  # noqa: E402

FUENTES = {
    "auditd": [("results/t5/auditd_completo_predicciones.csv", "alerta", "IF_auditd_completo"),
               ("results/t5/auditd_sin_clave_protegido_predicciones.csv", "alerta", "IF_auditd_sin_clave_protegido"),
               ("results/t6/predicciones_auditd.csv", "A1", "regla_A1"),
               ("results/t6/predicciones_auditd.csv", "A2", "regla_A2")],
    "apache": [("results/t5/apache_completo_predicciones.csv", "alerta", "IF_apache_completo"),
               ("results/t6/predicciones_apache.csv", "W1", "regla_W1"),
               ("results/t6/predicciones_apache.csv", "W2", "regla_W2"),
               ("results/t6/predicciones_apache.csv", "W3", "regla_W3")],
}
INDICE = "lab-alertas-offline"


def main():
    env = leer_env(".env")
    auth = "Basic " + base64.b64encode(f"lab_analyst:{env['ANALYST_PASSWORD']}".encode()).decode()
    lineas = []
    for fuente, archivos in FUENTES.items():
        for ruta, col, detector in archivos:
            if not os.path.exists(ruta):
                print(f"Falta {ruta}: se omite {detector}")
                continue
            with open(ruta, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r[col] != "1":
                        continue
                    _id = f"{fuente}-{detector}-{r['sesion']}-v{r['ventana']}"
                    doc = {"@timestamp": r["fin"], "event": {"kind": "alert", "module": "lab_detector"},
                           "lab": {"modo": "offline", "fuente": fuente, "detector": detector, "sesion": r["sesion"],
                                   "escenario": r["escenario"], "conjunto": r["conjunto"],
                                   "ventana_inicio": r["inicio"], "ventana_fin": r["fin"],
                                   "con_incidente": r["etiqueta"] == "1",
                                   "puntaje": float(r["puntaje"]) if r.get("puntaje") else None,
                                   "explicacion": r.get("explicacion", "")}}
                    lineas += [json.dumps({"create": {"_index": INDICE, "_id": _id}}), json.dumps(doc, ensure_ascii=False)]
    if not lineas:
        sys.exit("No hay alertas para cargar.")
    nuevas = existentes = errores = 0
    for i in range(0, len(lineas), 1000):
        cuerpo = ("\n".join(lineas[i:i + 1000]) + "\n").encode()
        req = urllib.request.Request(ES + "/_bulk?refresh=true", data=cuerpo, method="POST",
                                     headers={"Authorization": auth, "Content-Type": "application/x-ndjson"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read())
        for it in res["items"]:
            st = it["create"]["status"]
            if st == 201:
                nuevas += 1
            elif st == 409:
                existentes += 1
            else:
                errores += 1
                print("  error:", it["create"].get("error"))
    print(f"Alertas offline en {INDICE}: {nuevas} nuevas, {existentes} ya estaban, {errores} errores.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
