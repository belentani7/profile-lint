# Auditoría de restauración y verificación

- **Fecha:** 25 de noviembre de 2026
- **Rama de trabajo:** `arena/0041ab38-profile-lint`
- **Base:** `0a24a8b5a3648037c02e6ce36d06c2429d266a46`

Esta auditoría separa los hechos observados, los resultados locales y los puntos
que todavía requieren comprobación en GitHub. No implica que el código se haya
publicado en `main`.

## Fase 1 — Diagnóstico con evidencia

- El árbol de la base de trabajo contenía solamente `.gitignore`: no había
  paquete Python, manifiesto, README, pruebas ni workflow. `origin/main` también
  tenía únicamente `.gitignore`.
- El proyecto histórico está en `feat/stdin`, commit
  [`a38650825210c29afd79797c1f4c5419c4b3f42b`](https://github.com/belentani7/profile-lint/tree/a38650825210c29afd79797c1f4c5419c4b3f42b).
  Tiene historia sin ancestro común con la base de esta rama; por eso se
  restauraron y revisaron archivos explícitamente, sin merge ni cherry-pick.
- Ese árbol histórico documenta `profile-lint` 0.1.0, Python 3.9+, sin
  dependencias de ejecución, 16 pruebas unitarias y CI en Python 3.9/3.11/3.12.
  Sus resultados remotos sirven como antecedente, no como prueba de esta rama.
- La línea base local no podía validar el proyecto inexistente:
  `npm run build` terminó con `npm error code ENOENT` (faltaba
  `package.json`); `npm test` terminó con código 254 sin diagnóstico visible;
  `python -m unittest discover -s tests -v` informó
  `ImportError: Start directory is not importable: 'tests'`;
  `python -m build` informó `/usr/bin/python: No module named build`; y la CLI
  terminó con `ModuleNotFoundError: No module named 'profilelint'`. No se repiten
  comandos npm: el repositorio inspeccionado es Python, no Node.

## Fase 2 — Investigación y decisiones

- Se conservó Python 3.9 como versión mínima y se mantuvo la biblioteca estándar
  en tiempo de ejecución. El extra `dev` selecciona `build==1.4.2` en Python
  3.9 y `build==1.6.1` desde Python 3.10; Ruff se fija en `0.17.6`.
- La metadata usa ahora una expresión SPDX (`license = "MIT"`) y declara
  `license-files`, en lugar de la tabla de licencia obsoleta que produjo una
  advertencia de setuptools. `setuptools>=77.0.3` conserva soporte desde Python
  3.9 y entiende esa metadata.
- `html.parser` se usa para extraer atributos HTML, no como validador completo de
  marcado. `urllib.request` limita las comprobaciones opcionales a `HEAD` con
  timeout; la red queda desactivada por defecto. La concurrencia se limita al
  número de destinos únicos y al máximo configurable.
- La matriz prevista se verificó contra el manifiesto oficial de intérpretes:
  Python 3.15.2 ya figura como versión estable en la fecha de esta auditoría.
  Los jobs usan Ubuntu 22.04, `contents: read`, credenciales de checkout no
  persistentes y acciones fijadas a commits completos de las releases de
  `checkout` v7.0.1 y `setup-python` v7.1.0. Dependabot propone actualizaciones
  semanales de acciones y herramientas Python.

## Fase 3 — Cambios aplicados

| Área | Resultado verificable |
|---|---|
| Paquete/CLI | `profilelint`, versión 0.2.0; lectura de archivos o stdin, JSON, `--links`, límite de bytes, concurrencia configurable y códigos de salida 0/1/2. |
| Reglas | Encabezado y tamaño; alt text Markdown/HTML; afirmaciones de una lista explícita; enlaces y referencias Markdown, HTML y HTTP(S) simples; rutas locales, esquemas inseguros, imágenes remotas, widgets y estado HTTP opcional. |
| Fiabilidad | Deduplicación de URLs, rechazo conservador de `HEAD`, normalización de fragmentos, escape de destinos Markdown, comprobación de URL malformada y exclusión de código y comentarios de las reglas de contenido. |
| Pruebas | `tests/test_rules.py` comprueba la lógica sin solicitudes reales. `tests/test_cli.py` lanza la CLI en subprocesos para los recorridos felices de archivo y stdin, errores y formato JSON; además simula la capa HTTP. |
| Distribución/docs | `pyproject.toml`, README y política de seguridad en español, licencia MIT, exclusión de artefactos y construcción de `sdist` y wheel. |
| Automatización | CI para Python 3.9–3.15 en pushes y pull requests hacia `main`; lint, formato, pruebas, dogfooding del README y build; actualizaciones semanales mediante Dependabot. |

## Fase 4 — Verificaciones locales

Entorno de esta ejecución: **Python 3.11.2**. Resultados registrados tras los
cambios de código:

| Verificación | Resultado |
|---|---|
| `python -m unittest discover -s tests -v` (en `.venv`) | **61 pruebas aprobadas**, sin fallos. |
| `ruff check .` | Aprobado: `All checks passed!`. Ruff 0.17.6. |
| `ruff format --check .` | Aprobado; todos los archivos formateados. |
| `python -m compileall -q profilelint tests` | Aprobado, sin errores de sintaxis. |
| `python -m profilelint.cli README.md --root . --max-bytes 12000 --json` | Aprobado; README de **4.774 bytes**, 0 errores, 0 avisos. |
| `python -m build` | Aprobado: sdist y wheel `profile_lint-0.2.0`; backend aislado setuptools 84.2.1, sin la advertencia de licencia de la primera ejecución. |
| Instalación del wheel en un venv limpio e invocación de `profile-lint` | Aprobado en un fixture temporal; informe JSON con 0 errores/avisos. |
| YAML de CI y Dependabot | Parseados localmente con PyYAML 6.0.3; matriz y eventos correctos, y ambas acciones usan SHA completos de 40 caracteres. |
| `git diff --check` | Aprobado en la revisión local. |

Las herramientas se instalaron con `python -m pip install -e ".[dev]"`. La
metadata instalada confirma cero requisitos de ejecución; `build` y Ruff solo
pertenecen al extra de desarrollo.

## Fase 5 — Rendimiento y accesibilidad

### Rendimiento

Microbenchmark local sintético contra `profilelint/rules.py` del commit histórico
indicado arriba; medianas medidas con `time.perf_counter`, sin red real:

| Escenario | Histórico | Restauración | Cambio |
|---|---:|---:|---:|
| 2.400 destinos Markdown únicos, corpus de 122.592 bytes, sin comprobación HTTP | 0,101889 s | 0,080003 s | **1,27×** más rápido (−21,5 % de tiempo). |
| 32 destinos únicos y callback de estado simulado de 10 ms, serial vs. 8 workers | 0,323500 s | 0,042699 s | **7,58×** menos latencia total. |

Estas cifras son una comparación repetible del mismo entorno local, no una
predicción de producción ni una medición Lighthouse. El segundo escenario mide
concurrencia simulada, no disponibilidad ni latencia de servicios externos.

### Accesibilidad

No hay interfaz web ni aplicación cliente: Lighthouse y Core Web Vitals no son
métricas aplicables a este repositorio. En su lugar, siete casos específicos
cubren imágenes Markdown y HTML, `alt` ausente/booleano/solo con espacios,
atributos HTML sin comillas, `alt=""` decorativo e imágenes dentro de bloques
de código. La regla
acepta el `alt` vacío explícito de una imagen decorativa, pero falla si se omite
el atributo; sigue la orientación del estándar HTML. Esto comprueba presencia y
tratamiento del atributo, **no** certifica que la descripción sea adecuada ni
sustituye una auditoría de accesibilidad de la página renderizada.

## Fase 6 — Pendientes y límites

- La comprobación local se ejecutó con Python 3.11.2. El workflow declara una
  matriz de Python 3.9–3.15; el resultado remoto de cada versión debe consultarse
  en los checks del pull request de integración.
- No se probó `--links` contra hosts externos. Su comportamiento de HTTP está
  cubierto con respuestas simuladas; algunos servidores rechazan `HEAD`, aplican
  límites o pueden comportarse de forma distinta a `GET`. Esos estados se
  informan como no verificables cuando corresponde.
- La regla `claim` busca frases de una lista fija; no comprueba hechos ni
  determina automáticamente si una afirmación tiene evidencia suficiente.
- El analizador cubre las formas de Markdown/HTML documentadas en el README, no
  todos los dialectos, HTML roto ni todas las variantes de `srcset`.
- La API consultada no confirmó si el repositorio tiene habilitado el reporte
  privado de vulnerabilidades. `SECURITY.md` no invita a publicar un exploit y
  explica este límite; un propietario debe confirmar/habilitar un canal privado.
- La rama de trabajo de Arena es `arena/0041ab38-profile-lint`; se conserva como
  fuente de la entrega. La integración a `main` se tramita desde esta rama, sin
  cambiar de checkout ni hacer push directo a `main`.

## Fuentes consultadas

- [Python 3.11 — `html.parser`](https://docs.python.org/3.11/library/html.parser.html),
  [`urllib.request`](https://docs.python.org/3.11/library/urllib.request.html) y
  [`unittest`](https://docs.python.org/3.11/library/unittest.html): parser HTML,
  solicitudes `HEAD`/timeout y descubrimiento de pruebas.
- [Python Packaging User Guide — `pyproject.toml`](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
  y [especificación de metadata](https://packaging.python.org/en/latest/specifications/pyproject-toml/):
  formato SPDX y archivos de licencia.
  [PyPI setuptools 77.0.3](https://pypi.org/project/setuptools/77.0.3/) confirma
  compatibilidad declarada con Python 3.9+.
- [PyPI `build`](https://pypi.org/project/build/) y
  [Ruff 0.17.6](https://github.com/astral-sh/ruff/releases/tag/0.17.6):
  herramientas de construcción y lint usadas/fijadas.
- [Python 3.15.2](https://www.python.org/downloads/release/python-3152/) y
  [manifiesto de releases para Actions](https://github.com/actions/python-versions/releases/tag/3.15.2-40340363276):
  versión estable más reciente consultada para la matriz.
- [GitHub Actions — uso seguro de acciones](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions),
  [checkout v7.0.1, SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1)
  y [setup-python v7.1.0, SHA `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`](https://github.com/actions/setup-python/commit/6d4fd22b20465ccc0f7354476588e8df7c9ca0e0):
  ejecución y fijación inmutable de las acciones.
- [GitHub Docs — configurar el reporte privado de vulnerabilidades](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository):
  la opción debe activarla un propietario/administrador; esta auditoría no pudo
  confirmar su estado en el repositorio.
  [Referencia de `dependabot.yml`](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference):
  intervalo, hora y zona horaria usados en la configuración semanal.
- [WHATWG HTML Standard — imágenes y `alt`](https://html.spec.whatwg.org/multipage/images.html#alt):
  el atributo alternativo debe estar presente; el valor vacío es adecuado cuando
  la imagen es decorativa.
- [Historial `feat/stdin`](https://github.com/belentani7/profile-lint/tree/a38650825210c29afd79797c1f4c5419c4b3f42b):
  árbol de referencia usado para comparar historial, CI y rendimiento; no es la
  rama de entrega.
