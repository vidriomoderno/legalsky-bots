# Política de privacidad — LegalSky Bots

**Responsable:** LegalSky Reclamaciones Aereas (CIF B88315387), Plaza Mayor Ciudad Pegaso 11,
28022 Madrid, España. Contacto: legalskybarcelona@gmail.com.

**Qué es:** una herramienta interna de LegalSky. Solo la usa la propia empresa, con su cuenta
legalskybarcelona@gmail.com. No tiene usuarios externos.

**Qué datos usa:**

- **Gmail:** lee los correos con billetes y facturas de Iberia y Air Europa y les pone las
  etiquetas `LegalSky/Procesado` o `LegalSky/Revisar`. No envía ni borra correos.
- **Google Drive:** guarda los PDF de billetes y facturas en la carpeta de la empresa.
- **Google Sheets:** anota cada billete y factura en la hoja de control de la empresa.

**Para qué:** pedir y archivar las facturas de los billetes de la empresa y entregárselas a su
gestor.

**Con quién se comparten:** con nadie fuera de LegalSky. Los PDF se procesan con la API de
Claude (Anthropic) para leer sus datos, sin otro uso. El acceso a Google se guarda en el PC de
la empresa (`token.json`) y no se publica.

**Cómo retirar el acceso:** en https://myaccount.google.com/permissions, quitando "LegalSky Bots".

El uso de los datos recibidos de las APIs de Google cumple la
[Política de Datos del Usuario de los Servicios de las APIs de Google](https://developers.google.com/terms/api-services-user-data-policy),
incluidos los requisitos de uso limitado.
