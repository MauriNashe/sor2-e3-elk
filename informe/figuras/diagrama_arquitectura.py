"""Figura 1 del informe: arquitectura del laboratorio (genera arquitectura.png en esta carpeta).

Uso: python informe/figuras/diagrama_arquitectura.py   (necesita matplotlib)
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

AQUI = os.path.dirname(os.path.abspath(__file__))

# Paleta: un tono por rol
C_HOST, C_VM, C_GEN, C_FUENTE, C_INGESTA, C_DOCKER, C_ELK, C_PY = (
    "#EEF1F5", "#F7F9FC", "#FFF4E0", "#E6F2EA", "#E8EEF9", "#EEF6FB", "#DCEBF7", "#F4E8F7")
BORDE, TEXTO, FLECHA = "#5B6573", "#1F2933", "#3E4C59"

fig, ax = plt.subplots(figsize=(10.5, 6.6))
ax.set_xlim(0, 16)
ax.set_ylim(0, 9.4)
ax.axis("off")


def caja(x0, y0, x1, y1, color, titulo, texto="", borde=BORDE, lw=1.2, ls="-", tam=11.5, alineacion="center",
         titulo_arriba=False):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=color, ec=borde, lw=lw, ls=ls))
    if titulo_arriba:
        ax.text(x0 + 0.15, y1 - 0.12, titulo, ha="left", va="top", fontsize=tam, fontweight="bold", color=TEXTO)
        return
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if texto:
        ax.text(cx, cy + 0.06, titulo, ha="center", va="bottom", fontsize=tam, fontweight="bold", color=TEXTO)
        ax.text(cx, cy - 0.02, texto, ha="center", va="top", fontsize=tam - 1.5, color=TEXTO, linespacing=1.25,
                multialignment=alineacion)
    else:
        ax.text(cx, cy, titulo, ha="center", va="center", fontsize=tam, fontweight="bold", color=TEXTO)


def flecha(p0, p1, texto="", dx=0.0, dy=0.12, estilo="-|>", ls="-", curva=0.0, tam=9.5):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=estilo, mutation_scale=13, lw=1.3, color=FLECHA, ls=ls,
                                 connectionstyle=f"arc3,rad={curva}", shrinkA=2, shrinkB=2))
    if texto:
        ax.text((p0[0] + p1[0]) / 2 + dx, (p0[1] + p1[1]) / 2 + dy, texto, ha="center", va="bottom", fontsize=tam,
                color=FLECHA, style="italic")


# ------------------------------------------------------------------ anfitrión
caja(0.15, 0.25, 2.75, 9.15, C_HOST, "Windows 11\n(Hyper-V)", titulo_arriba=True)
caja(0.4, 6.9, 2.5, 8.0, "white", "PowerShell", "SSH y\nadministración")
caja(0.4, 0.4, 2.5, 1.6, "white", "Navegador", "Kibana")

# ------------------------------------------------------------------ máquina virtual
caja(3.05, 0.25, 15.85, 9.15, C_VM,
     "VM Ubuntu 24.04 · 192.168.56.10 · 4 vCPU, 8 GB · un único reloj (chrony)",
     titulo_arriba=True, lw=1.6)

# generación
caja(3.6, 7.05, 6.2, 8.35, C_GEN, "lote.py", "plan con semilla\nverifica cada sesión")
caja(3.6, 4.75, 6.2, 6.25, C_GEN, "labuser", "linux_actividad.py\nB1 e I1")
caja(3.6, 2.3, 6.2, 3.8, C_GEN, "Clientes HTTP", "benignos (B2)\ny atacante (I2)")

# fuentes
caja(6.75, 4.75, 8.85, 6.25, C_FUENTE, "auditd", "lab.rules\naudit.log")
caja(6.75, 2.3, 8.85, 3.8, C_FUENTE, "Apache 2.4", "access.log")

# ingestión
caja(9.3, 3.55, 11.0, 5.0, C_INGESTA, "Filebeat", "auditd y\napache")

# Python
caja(6.75, 0.85, 11.0, 2.05, C_PY, "Python (lab_analyst)",
     "ventanas · Isolation Forest · reglas\ndetector en vivo (cada 30 s)")

# Elastic Stack en Docker
caja(11.35, 0.45, 15.6, 8.55, C_DOCKER, "Docker · Elastic Stack 9.5.6", titulo_arriba=True, ls="--")
caja(11.65, 6.55, 15.3, 7.85, C_ELK, "Logstash :5044", "marcas y enrutado\npor fuente")
caja(11.65, 3.55, 15.3, 5.75, C_ELK, "Elasticsearch :9200",
     "pipelines ECS\nlab-auditd-*, lab-apache-*\nlab-alertas-*")
caja(11.65, 0.8, 15.3, 2.05, C_ELK, "Kibana :5601", "Discover y tablero")

# ------------------------------------------------------------------ flujos
flecha((4.9, 7.05), (4.9, 6.25), "lanza", dx=0.35, dy=-0.12)
ax.plot([3.6, 3.33, 3.33], [7.5, 7.5, 3.05], color=FLECHA, lw=1.3)
flecha((3.33, 3.05), (3.6, 3.05))
ax.text(3.45, 4.3, "lanza", rotation=90, ha="center", va="center", fontsize=9.5, color=FLECHA, style="italic")
flecha((6.2, 5.5), (6.75, 5.5))
flecha((6.2, 3.05), (6.75, 3.05), "HTTP", dy=-0.42)
flecha((8.85, 5.5), (9.3, 4.6))
flecha((8.85, 3.05), (9.3, 3.95))
flecha((11.0, 4.6), (11.65, 7.0), "Beats", dx=-0.25, dy=0.0)
flecha((13.45, 6.55), (13.45, 5.75), "eventos", dx=0.55, dy=-0.15)
flecha((13.45, 3.55), (13.45, 2.05), "consultas", dx=0.55, dy=-0.15)
flecha((11.65, 3.95), (10.8, 2.05))
ax.text(10.95, 2.95, "lee", ha="right", va="center", fontsize=9.5, color=FLECHA, style="italic")
flecha((11.0, 1.45), (11.65, 3.7), ls="--")
ax.text(10.95, 2.5, "escribe\nalertas", ha="right", va="center", fontsize=9.5, color=FLECHA, style="italic")
flecha((2.5, 7.45), (3.6, 7.85), "SSH :22", dx=-0.05, dy=0.1)
ax.plot([13.45, 13.45], [0.8, 0.6], color=FLECHA, lw=1.3)
flecha((13.45, 0.6), (2.5, 0.6), "HTTP :5601", dx=-3.5, dy=0.02)

plt.tight_layout(pad=0.2)
salida = os.path.join(AQUI, "arquitectura.png")
plt.savefig(salida, dpi=200)
print("Figura:", salida)
