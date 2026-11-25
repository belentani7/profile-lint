# profile-lint

`profile-lint` audita un README de perfil de GitHub antes de publicarlo: busca
rutas locales inexistentes, enlaces potencialmente rotos, imágenes sin texto
alternativo y afirmaciones que conviene respaldar con evidencia. Es una
herramienta de terminal, determinista y sin dependencias de ejecución.

## Instalación rápida

Requiere Python 3.9 o posterior.

```bash
python -m pip install .
profile-lint README.md --root .
```

La comprobación predeterminada es local y no accede a la red. Para pedir el
estado de los enlaces externos mediante solicitudes `HEAD`:

```bash
profile-lint README.md --root . --links
```

Para revisar un README recibido por entrada estándar, sin crear un archivo:

```bash
gh api repos/usuario/usuario/readme \
  -H "Accept: application/vnd.github.raw" | profile-lint - --root .
```

Se puede generar una salida estable para otros programas o para CI:

```bash
profile-lint README.md --root . --json
```

`--link-workers` limita las consultas simultáneas cuando se usa `--links` (por
defecto, ocho). Cada petición tiene un tiempo de espera de ocho segundos.

## Reglas

| Regla | Severidad | Qué detecta |
|---|---|---|
| `empty` | error | El archivo no contiene texto. |
| `heading` | aviso | Falta un encabezado de nivel 1 (`# Título`). |
| `alt-text` | error | Una imagen Markdown no tiene texto alternativo, una imagen HTML omite `alt` o el valor solo contiene espacios. Un `alt=""` explícito en HTML se acepta para imágenes decorativas. |
| `remote-image` | aviso | Una imagen se descarga desde otro host al mostrar el README. |
| `widget` | aviso | Un enlace depende de un servicio externo de insignias o estadísticas. |
| `claim` | error | Aparece una frase promocional de una lista fija que no se puede verificar por sí sola. |
| `size` | aviso | El README supera el presupuesto en bytes (12.000 por defecto). |
| `missing-path` | error | Un enlace o imagen local apunta a una ruta inexistente. |
| `scheme` | error | Un enlace usa un esquema peligroso o no admitido. Se admiten rutas relativas, `http`, `https`, `mailto` y `tel`. |
| `dead-link` | error | Con `--links`, un destino externo responde con un error de cliente verificable. |
| `unverified-link` | aviso | El servidor rechaza `HEAD`, limita el acceso o devuelve un error temporal; no se afirma que el recurso haya desaparecido. |

Las rutas relativas se resuelven desde la carpeta del README, o desde `--root`
si se especifica. Para `stdin`, hay que pasar `--root` si también se quieren
comprobar enlaces locales. Se reconocen enlaces Markdown en línea y de
referencia, enlaces HTML y autoenlaces HTTP(S). El contenido de bloques y spans
de código, así como los comentarios HTML, no se trata como contenido ejecutable
del README.

`--links` considera que los códigos HTTP 401, 403, 405, 408, 429 y 451, además
del código no estándar 999, no son prueba suficiente de que un enlace esté roto.
También clasifica las respuestas 5xx como no verificables. El resto de respuestas
4xx se informa como error.

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | No hay errores; los avisos no bloquean. |
| `1` | Hay al menos un error en el README. |
| `2` | No se pudo leer el archivo o la ruta no es un archivo. |

## Uso en GitHub Actions

La integración continua ejecuta lint, pruebas, una comprobación del propio
README y la construcción del paquete en Python 3.9–3.15.

```yaml
- name: Instalar herramientas de desarrollo
  run: python -m pip install -e ".[dev]"
- name: Lint
  run: ruff check .
- name: Pruebas unitarias y de CLI
  run: python -m unittest discover -s tests -v
- name: Construir el paquete
  run: python -m build
```

Las herramientas de desarrollo (`build` y Ruff) son opcionales; no se instalan
como dependencias de ejecución del paquete.

## Desarrollo

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m profilelint.cli README.md --root .
python -m build
```

El núcleo está en `profilelint/rules.py`; las pruebas de reglas y del recorrido
de CLI están en `tests/test_rules.py` y `tests/test_cli.py`.

## Límites conocidos

- La comprobación externa usa `HEAD`. Algunos hosts lo bloquean aunque una
  persona pueda abrir la página; esos casos quedan como no verificables.
- Las afirmaciones se detectan con una lista fija. Esta herramienta no confirma
  hechos ni evalúa la calidad del software enlazado.
- No se analizan todos los dialectos de Markdown ni todas las variantes de
  `srcset`; el objetivo es revisar los enlaces e imágenes habituales de un
  README de perfil sin depender de una biblioteca de terceros.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
