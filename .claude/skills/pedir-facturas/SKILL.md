---
name: pedir-facturas
description: Ejecuta ahora el bot de facturas de LegalSky - lee los billetes y facturas nuevos del Gmail de compras y pide en Iberia y Air Europa las facturas pendientes con Claude in Chrome. Usar cuando el usuario pida pedir/solicitar facturas, ejecutar o lanzar el bot, o escriba /pedir-facturas. Con el argumento "prueba" rellena los formularios sin enviarlos.
---

# Pedir facturas ahora

**Regla general: LegalSky es una empresa en ESPAÑA** (facturas a nombre de la sociedad,
CIF y domicilio fiscal en España).

Trabaja en la carpeta del proyecto. Si el argumento es `prueba`, rellena los formularios
pero **no pulses el botón final de enviar** y anota cada billete como `revisar` con el
detalle "prueba: formulario listo, no enviado".

## 1. Leer el Gmail de compras

```
python -m legalsky_bots.main
```

Registra en la hoja de control los billetes y facturas nuevos (bots 1 y 3). Si falla por
configuración (falta `.env`, `token.json` o una variable), para y explica al usuario qué
falta según el README ("Puesta en marcha"). Si solo hay errores de algún PDF, sigue.

## 2. Pedir las facturas pendientes

Sigue `tarea_pc/INSTRUCCIONES.md` paso a paso, usando Claude in Chrome. Empieza por
`python scripts/cola_pc.py pendientes`. Si no hay billetes, dilo y termina.

Antes de abrir Chrome, carga las herramientas de Claude in Chrome con una sola búsqueda de
herramientas y trabaja en pestañas nuevas.

## 3. Resumen

Ejecuta `python scripts/cola_pc.py resumen` y cuenta al usuario, en pocas líneas:
cuántas facturas se pidieron, cuáles quedaron para revisar y por qué, y cuántos billetes
siguen esperando (por ejemplo, Air Europa antes de 48 h).
