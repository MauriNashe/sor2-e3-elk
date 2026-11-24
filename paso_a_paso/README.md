# Paso a paso

Una guía por etapa del trabajo. Cada paso indica **qué hace**, el **comando** y **qué debería devolver**.
Las guías se siguen en orden: cada una parte del estado en que dejó la anterior.

**Dónde se ejecuta cada comando:**
- 🪟 **PowerShell en Windows** (el equipo anfitrión). El prompt empieza con `PS C:\...>`.
- 🐧 **Dentro de la VM**, por SSH. El prompt es `labadmin@sor2-lab:~$`.

> Regla rápida: los comandos con rutas `C:\...` van en Windows; los que usan `~/`, `sudo` o `docker` van en la VM.

## Copiar el repo actualizado a la VM 🪟

Se usa en varias guías. Empaqueta el repo **sin la carpeta `.git`** y lo desempaqueta en la VM sobre la copia
existente. No pisa el `.env` ni los resultados que solo existen en la VM.

```powershell
cmd /c "tar -cf - --exclude=.git -C C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml . | ssh labadmin@192.168.56.10 tar -xf - -C sor2-e3-elk-ml"
```

**Resultado:** pide la contraseña de `labadmin` y termina sin mensajes (puede mostrar avisos de `tar` sobre fechas, que no importan).

> Por qué no `scp -r`: copia también `.git`, cuyos objetos quedan de solo lectura en la VM, y la segunda vez falla con
> *Permission denied* en `.git/objects/...` (el resto de los archivos sí se copia). Se usa `cmd /c` porque PowerShell 5.1
> altera los datos binarios que pasan por un `|` entre programas.

| Guía | Etapa | Estado |
|---|---|---|
| [01 — Laboratorio](01_laboratorio.md) | T1: Hyper-V, VM, ELK seguro, pruebas e inventario | ✅ |
| [02 — Ingesta](02_ingesta.md) | T2: reglas de auditd, Filebeat, pipelines, plantilla e índices | ✅ parte mínima (falta la documentación de campos) |
| [03 — Escenarios](03_escenarios.md) | T3: generadores, piloto y lote de sesiones | ✅ lote 40/40 |
| [04 — Ventanas y características](04_ventanas.md) | T4: datasets por fuente en ventanas de 30 s | ✅ 120 + 120 ventanas |
| [05 — Isolation Forest](05_isolation_forest.md) | T5: un detector por fuente, umbral en validación, evaluación en prueba | ✅ 3 modelos |
| [06 — Reglas](06_reglas.md) | T6: baseline por reglas y comparación con Isolation Forest | ✅ |
| [07 — Alertas y latencia](07_vivo.md) | T7: detector en vivo, cronología, latencia y CPU/RAM | ✅ (falta la captura de Kibana) |
| [08 — Evaluación y dashboard](08_evaluacion.md) | T8: pérdidas, dashboard NDJSON, tablas y gráficos | ✅ |
