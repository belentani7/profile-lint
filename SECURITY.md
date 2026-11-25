# Política de seguridad

`profile-lint` es una herramienta local y no inicia conexiones de red de forma
predeterminada. La opción `--links` sí hace solicitudes HTTP `HEAD` a los URL
externos escritos en el README auditado.

## Notificación de vulnerabilidades

No publiques detalles de vulnerabilidades sin corregir en incidencias públicas.
Si GitHub ofrece la opción **Report a vulnerability** para este repositorio, úsala
para crear un aviso privado:
[belentani7/profile-lint/security/advisories/new](https://github.com/belentani7/profile-lint/security/advisories/new).
Incluye la versión afectada, el impacto y los pasos mínimos para reproducirla.

La API consultada durante esta restauración no confirmó si la notificación privada
está habilitada. Si no aparece el formulario, no publiques la prueba de concepto
ni detalles explotables: solicita a los mantenedores que habiliten la notificación
privada y acuerda un canal privado antes de divulgar la vulnerabilidad. No se
ofrece un plazo de respuesta ni un programa de recompensas.
