# Bot de Marangatu: investigación previa al diseño (D-119)

Consultado el 2026-11-25. Lo leí yo, sin agentes de investigación; los PDF se extrajeron con
`pdftotext`. La D-119 dejó tres preguntas abiertas antes del diseño:

1. ¿El portal tiene captcha o segundo factor?
2. ¿Las condiciones de uso admiten el acceso automatizado?
3. ¿Hay un servicio web oficial para alguna de estas operaciones?

## 1. Fuentes leídas

- **Resolución N° 568/2006 (SET)**: «Por la cual se establecen las condiciones generales de
  responsabilidad y uso de medios electrónicos para la presentación de información tributaria».
  - Del 15 de marzo de 2006, 8 páginas, con el texto leído completo.
  - Es la que la DNIT lista hoy en su página «Clave de Acceso».
  - Enlace: <https://www.dnit.gov.py/documents/20123/209444/Resoluci%C3%B3n+N%C2%BA+0568_06.pdf/12154daf-c2a6-edbc-a27c-788d84cd142c?t=1682698139300>
- **Guía «Cómo cambiar la Clave de Acceso» / «Cómo solicitar el cambio de su clave por olvido –
  Código Captcha»** (DNIT): 11 páginas, con el texto leído.
  - Enlace: <https://www.dnit.gov.py/documents/20123/209444/Gu%C3%ADa+paso+a+paso++Marangatu+-+C%C3%B3mo+solicitar+el+cambio+de+su+clave++por+olvido+-+C%C3%B3digo+Captcha.pdf/80fb0c6e-4134-9b99-1db7-cc39ef1af17b?t=1682698141448>
- **Resolución General N° 04/2007**: reglamenta la obtención y la modificación de la clave.
  - **No se pudo leer.** El PDF es un escaneo sin texto y no hay OCR instalado.
  - Enlace: <https://www.dnit.gov.py/documents/20123/209444/Resoluci%C3%B3n+General+N%C2%BA+04_07.pdf/91aec63b-ab3b-90b1-9ceb-424a46944d43?t=1682698139995>
- **Páginas «Clave de Acceso», «Sistema Marangatu» y «Servicios Online – Cómo utilizarlos»** de
  dnit.gov.py: no dicen nada sobre captcha, segundo factor, condiciones de uso ni acceso
  automatizado.

## 2. Lo que dice la Resolución 568/2006

- **Art. 5:** las declaraciones presentadas por la página web «equivaldrán a las declaraciones
  físicas en papel firmadas por el interesado en forma manuscrita».
- **Art. 7:** la clave «tendrá carácter estrictamente personal y será secreta e intransferible».
  - Su uso es de «exclusiva responsabilidad del sujeto pasivo titular».
  - De ella se derivan «todas las responsabilidades de carácter legal y tributario que hoy se
    desprenden de la firma autógrafa».
  - El titular debe «tomar las medidas de seguridad necesarias para mantener su clave bajo
    estricto control y evitar toda utilización no autorizada».
- **Art. 8:** «Si el sujeto pasivo no recibe el acuse de recibo o confirmación de recepción
  inmediatamente después de su presentación, deberá considerar a su información como no
  presentada», salvo que lo confirme en la consulta por Internet. El acuse no implica
  conformidad con el contenido.
- **Art. 6 y art. 10:** hay que imprimir y conservar la declaración y el acuse de recepción o de
  rechazo durante la prescripción. Además, hay que conservar «un registro cronológico completo de
  todos los mensajes electrónicos intercambiados», sin modificar y protegido.
- **Art. 11 (el punto delicado):** los sujetos pasivos quedan «prohibidos de intervenir o
  manipular, mediante la utilización de programas o de cualquier otra manera, el software provisto
  por la Administración Tributaria y el sitio Web de la Subsecretaría de Estado de Tributación».
- **Art. 12:** si el contribuyente usa servicios de terceros para transmitir o procesar, la
  responsabilidad por los daños se resuelve entre las partes. La DNIT no responde.
- **Art. 13:** la DNIT puede cambiar el software y el sitio sin aviso previo.

## 3. Respuestas a las preguntas de la D-119

1. **Captcha y segundo factor:** según la guía, el ingreso es con el usuario (RUC sin DV) y la
   clave. Al **tercer intento fallido** pide además un captcha («No soy un robot»).
   - No se encontró ningún segundo factor.
   - La recuperación de la clave va por un enlace al correo principal.
   - Consecuencia: el bot nunca reintenta un ingreso fallido. Con un solo «usuario o contraseña
     incorrectos» se detiene y avisa, porque no puede ni debe resolver un captcha.
2. **Acceso automatizado:** la Resolución 568/2006 no lo autoriza en forma expresa. Su art. 11
   prohíbe «intervenir o manipular, mediante la utilización de programas», el sitio web.
   - **Lectura estricta:** un programa que maneja el sitio en lugar de la persona cae ahí, y el
     bot de la D-119 estaría prohibido.
   - **Lectura amplia:** la norma apunta a alterar el sitio o el software (manipularlos). Un
     navegador que llena los mismos formularios que llenaría la persona, con su propia clave y
     en su propia computadora, no altera nada.
   - El texto no resuelve cuál de las dos rige, y no se encontró una consulta de la DNIT sobre
     esto.
   - **Es una decisión del propietario, no técnica:** las declaraciones que presenta el bot son
     suyas, con la responsabilidad de su firma (art. 5 y art. 7).
   - La clave no se transfiere: la herramienta corre en la computadora del propietario y la
     guarda en su almacén de credenciales.
3. **Servicio web oficial:** no se encontró uno para presentar declaraciones juradas.
   - Hay software de la DNIT para declaraciones informativas (Hechauka, con especificación técnica
     publicada) y una «Especificación Técnica de Consultas Públicas».
   - El SIFEN (factura electrónica) sí es un servicio web oficial, pero lo emite el
     contribuyente, no es para declarar.

## 4. Lo que esto cambia en el diseño, sea cual sea la decisión

- **Ingreso:** un solo intento, nunca captcha. Con cualquier error de ingreso se detiene.
- **Acuse obligatorio (art. 8):** sin acuse inmediato, la presentación se considera **no hecha**.
  - El bot no la marca presentada.
  - Revisa la consulta de Marangatu antes de cualquier reintento, para no duplicar (condición 5
    de la D-119).
- **Registro (art. 10):** el registro de pasos y capturas de la D-119 (condición 10) se guarda
  sin modificar y protegido durante la prescripción, igual que la declaración y el acuse.
- **Cambios del portal (art. 13):** el sitio cambia sin aviso. Eso refuerza la condición 7: el bot
  se detiene ante cualquier pantalla que no reconozca.

## 5. Pendiente

- ~~Decisión del propietario sobre el art. 11.~~ Resuelta en la D-126: lectura amplia, el bot sigue, y la guía paso a paso como alternativa.
- Leer la RG 04/2007, que necesita OCR o una copia con texto.
- Buscar si hay una consulta vinculante de la DNIT sobre el uso de programas para operar
  Marangatu.
