# Carpeta destinada a la elaboración de códigos y edición de los mismos mediante Virtual Studio Code.
## Tenemos los archivos:
- settings.json -> Empleado para definir las preferencias del workspace. (Es recomendable verlo y cambiar la configuración específica)
- launch.json -> Empleado para las configuraciones de depuración, concretamente para el Run y Debug del VS Code.
## Activación
`ctrl + shift + p` en el VS Code para seleccionar el intérprete de python:

<img width="462" height="436" alt="image" src="https://github.com/user-attachments/assets/a074f67b-f356-482e-be58-ddedf769b130" />

Aquí, seleccionamos el gis:

<img width="451" height="149" alt="image" src="https://github.com/user-attachments/assets/1040e3c4-d4d8-4291-8f81-dc17dd97f0f6" />


## Verificación
Si nos sale algo como lo siguiente al configurar VS Code:
<img width="2048" height="326" alt="image" src="https://github.com/user-attachments/assets/521defa7-ee0a-4a53-9d31-1fcc0b57bbea" />
Debemos ejecutar el comando: 
 ```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
 ```
Con esto permitimos scripts en nuestra sesión, pero sólo para nuestro usuario actual.
En caso de ser necesario, habrá que cerrar todas las terminales de VS Code y volver a abrir una nueva.
