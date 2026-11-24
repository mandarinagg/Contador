# Restaurar una copia de seguridad (Windows 11)

Guía para el propietario. Sirve si la base de datos se dañó, si el disco falló o si instalás Contador AI en otra PC y querés recuperar la contabilidad.

> **Estado:** hoy la restauración se hace a mano, con este procedimiento. Restaurar desde la propia aplicación todavía no existe. La restauración con las herramientas de PostgreSQL está probada automáticamente (`desktop/src-tauri/tests/backup.rs`: copia, restauración en una base nueva y backend arrancando sobre ella); en Windows la ejecuta el CI. Pero los pasos de esta guía escritos para PowerShell **todavía no se probaron a mano en una PC con Windows 11**. Hacelos con calma y, si algo no coincide con lo que ves, **frená y pedí ayuda técnica**.

## Dónde está cada cosa

| Qué | Ruta |
|---|---|
| Programa instalado (instalador por usuario, sin administrador) | `%LOCALAPPDATA%\Contador AI` (por ejemplo `C:\Users\TuUsuario\AppData\Local\Contador AI`) |
| Herramientas de PostgreSQL (`pg_restore.exe`, `psql.exe`, …) | `%LOCALAPPDATA%\Contador AI\pgsql\bin` |
| Datos de la contabilidad (la base) | `%LOCALAPPDATA%\ContadorAI\pgdata` |
| **Copias automáticas** | `%LOCALAPPDATA%\ContadorAI\backups\auto\contador-AAAAMMDD-HHMMSS.dump` |
| Registro de las copias (errores incluidos) | `%LOCALAPPDATA%\ContadorAI\logs\backup.log` |
| Contraseña de la base | Administrador de credenciales de Windows (entrada de `ContadorAI`, ver paso 3) |

Notas:
- `%LOCALAPPDATA%` es una carpeta oculta del usuario. Para abrirla: tecla Windows + R, escribí `%LOCALAPPDATA%` y Enter.
- La carpeta del programa la define el instalador de Tauri (NSIS) en modo "por usuario": `$LOCALAPPDATA\<nombre del producto>`, y el producto se llama "Contador AI" (se verificó en el código del instalador de Tauri, `installer.nsi`, y en la prueba del CI, que busca `pgsql\bin\postgres.exe` dentro de la carpeta instalada). **No** usa `Program Files` ni `AppData\Local\Programs`. Si en tu PC se eligió otra carpeta al instalar, para confirmarlo: clic derecho en el acceso directo de Contador AI → "Abrir ubicación del archivo". La carpeta `pgsql\bin` está dentro de esa ubicación.
- La app guarda **una copia por día** (la primera vez que se abre en el día) y conserva las últimas **14**. Si falta alguna, mirá `backup.log`.

## Advertencias importantes

1. **No borres `pgdata`** (ni la carpeta `ContadorAI`) si no tenés una copia de seguridad probada **afuera de esa carpeta**. `pgdata` es la contabilidad viva.
2. **Las copias están en el mismo disco que la base.** Si el disco falla, se pierden las dos cosas. Copiá cada tanto la carpeta `backups\auto` a un pendrive o disco externo (o a una carpeta sincronizada).
3. **Las copias no están cifradas todavía** (pendiente, ver `docs/SECURITY.md`). Cualquiera que tenga un archivo `.dump` puede leer la contabilidad. Guardalas solo en lugares de confianza.
4. **Nunca se restaura encima de la base en uso.** Este procedimiento carga la copia en una base **nueva** y recién después la pone en lugar de la anterior; la anterior **no se borra**, queda guardada con otro nombre.
5. Usá una versión de Contador AI **igual o más nueva** que la que hizo la copia. La app actualiza sola la estructura de la base al abrirse, pero no puede abrir una base de una versión más nueva que ella.
6. Si movés o renombrás `pgdata` para que la app arme una base vacía, la app genera una contraseña **nueva** y reemplaza la guardada en Windows: la `pgdata` vieja deja de poder abrirse con la contraseña actual. Antes de hacer eso asegurate de tener la copia `.dump` y de haber copiado toda la carpeta `ContadorAI` a otro lugar.

## Antes de empezar

1. Elegí la copia a restaurar: normalmente la más reciente de `%LOCALAPPDATA%\ContadorAI\backups\auto`. **Copiala** a otra carpeta (por ejemplo `C:\Restauracion\`) y trabajá con esa copia.
2. **Si la PC es nueva o se reinstaló:** instalá Contador AI, abrilo una vez hasta que muestre la pantalla de configuración inicial (con eso crea una base vacía y su contraseña) y cerralo. **No hagas la configuración inicial**: los datos van a venir de la copia.
3. **Cerrá Contador AI por completo.** Al cerrarlo se detienen el backend y PostgreSQL.
4. Con la app cerrada, copiá la carpeta `%LOCALAPPDATA%\ContadorAI` completa a un disco externo o a otra carpeta. Es tu red de seguridad.

## Pasos

Abrí **PowerShell** (menú Inicio → "PowerShell"). Los comandos son para copiar y pegar de a uno; cambiá solo la línea de la copia.

### 1. Variables

```powershell
$pg    = "$env:LOCALAPPDATA\Contador AI\pgsql\bin"
$datos = "$env:LOCALAPPDATA\ContadorAI"
$copia = "C:\Restauracion\contador-AAAAMMDD-HHMMSS.dump"   # <- poné el nombre real de tu copia
Test-Path "$pg\pg_restore.exe", "$datos\pgdata\PG_VERSION", $copia   # las tres deben dar True
```

Si alguna da `False`, no sigas: revisá la ruta (ver la tabla de arriba).

### 2. Comprobar que la copia se puede leer

```powershell
& "$pg\pg_restore.exe" --list $copia | Select-Object -First 15
```

Debe mostrar una lista (líneas con `TABLE`, `SCHEMA`, etc.). Si da error, esa copia está dañada: probá con la anterior.

### 3. Contraseña de la base

Panel de control → **Administrador de credenciales** → **Credenciales de Windows** → buscá la entrada de `ContadorAI` (su nombre incluye `postgresql` y `ContadorAI`) → **Mostrar** (te pide la contraseña de tu usuario de Windows). Son 64 caracteres.

```powershell
$env:PGPASSWORD = "pegá-acá-la-contraseña"
```

La variable vale solo en esta ventana de PowerShell; al cerrarla desaparece. Si la entrada no existe, **no sigas** y pedí ayuda técnica: sin ella no se puede abrir la base actual.

### 4. Encender PostgreSQL a mano (con la app cerrada)

```powershell
& "$pg\pg_ctl.exe" start -D "$datos\pgdata" -w -t 60 -l "$datos\logs\restauracion-pg.log" -o "-p 55440 -c listen_addresses=127.0.0.1"
```

Debe terminar con `server started`.

### 5. Cargar la copia en una base **nueva**

```powershell
& "$pg\createdb.exe" -h 127.0.0.1 -p 55440 -U contador --no-password contador_restaurada
& "$pg\pg_restore.exe" -h 127.0.0.1 -p 55440 -U contador --no-password --exit-on-error --single-transaction --no-owner -d contador_restaurada $copia
```

Si `createdb` dice que la base ya existe, quedó un intento anterior: pedí ayuda técnica antes de seguir. Si `pg_restore` da error, la carga se deshace sola; la base `contador_restaurada` queda vacía y se puede descartar con `& "$pg\dropdb.exe" -h 127.0.0.1 -p 55440 -U contador --no-password contador_restaurada` (esa base es nueva, no tiene datos tuyos).

### 6. Comprobar que están los datos

```powershell
& "$pg\psql.exe" -h 127.0.0.1 -p 55440 -U contador --no-password -d contador_restaurada -c "select legal_name from core.organizations"
```

Debe aparecer el nombre de tu empresa. Si no aparece, **no sigas** al paso 7.

### 7. Poner la base restaurada en lugar de la actual (sin borrar nada)

La app siempre usa la base llamada `contador`. Se intercambian los nombres y la anterior queda guardada:

```powershell
& "$pg\psql.exe" -h 127.0.0.1 -p 55440 -U contador --no-password -d postgres -c "ALTER DATABASE contador RENAME TO contador_anterior_AAAAMMDD"
& "$pg\psql.exe" -h 127.0.0.1 -p 55440 -U contador --no-password -d postgres -c "ALTER DATABASE contador_restaurada RENAME TO contador"
```

Reemplazá `AAAAMMDD` por la fecha de hoy. Si el primer comando dice que la base "está siendo utilizada", la app o el backend siguen abiertos: cerralos (Administrador de tareas) y repetí.

### 8. Apagar PostgreSQL y abrir la app

```powershell
& "$pg\pg_ctl.exe" stop -D "$datos\pgdata" -m fast -w
Remove-Item Env:\PGPASSWORD
```

Abrí Contador AI normalmente, ingresá con tu usuario de siempre y revisá que los datos estén.

### 9. Después

- Dejá la base `contador_anterior_AAAAMMDD` por un tiempo (solo ocupa espacio en disco). No la borres hasta estar seguro de que todo está bien; borrarla requiere ayuda técnica.
- Anotá qué copia usaste y por qué.

## Si algo sale mal

- Cualquier paso que falle: **frená**. Hasta el paso 7 no se cambió nada de la base actual; después del paso 7 se vuelve atrás intercambiando los nombres otra vez (con PostgreSQL encendido como en el paso 4).
- Compartí con quien te ayude: `%LOCALAPPDATA%\ContadorAI\logs\backup.log`, `postgresql.log` y `restauracion-pg.log`. **No** compartas la contraseña ni los archivos `.dump`.
