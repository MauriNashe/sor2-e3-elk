# Paso a paso

Una guía por etapa del trabajo. Cada paso indica **qué hace**, el **comando** y **qué debería devolver**.
Las guías se siguen en orden: cada una parte del estado en que dejó la anterior.

**Dónde se ejecuta cada comando:**
- 🪟 **PowerShell en Windows** (el equipo anfitrión). El prompt empieza con `PS C:\...>`.
- 🐧 **Dentro de la VM**, por SSH. El prompt es `labadmin@sor2-lab:~$`.

> Regla rápida: los comandos con rutas `C:\...` van en Windows; los que usan `~/`, `sudo` o `docker` van en la VM.

| Guía | Etapa | Estado |
|---|---|---|
| [01 — Laboratorio](01_laboratorio.md) | T1: Hyper-V, VM, ELK seguro, pruebas e inventario | ✅ |
| [02 — Ingesta](02_ingesta.md) | T2: reglas de auditd, Filebeat, pipelines, plantilla e índices | En curso |
| 03 — Escenarios | T3: generadores, piloto y lote de sesiones | Pendiente |
| 04 — Ventanas y características | T4 | Pendiente |
| 05 — Isolation Forest | T5 | Pendiente |
| 06 — Reglas | T6: baseline por reglas | Pendiente |
| 07 — Alertas y latencia | T7 | Pendiente |
| 08 — Evaluación y dashboard | T8 | Pendiente |
