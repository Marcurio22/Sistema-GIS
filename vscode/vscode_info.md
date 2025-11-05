# Carpeta destinada a la elaboración de códigos y edición de los mismos mediante Virtual Studio Code.
## Tenemos los archivos:
- settings.json -> Empleado para definir las preferencias del workspace. (Es recomendable verlo y cambiar la configuración específica)
- launch.json -> Empleado para las configuraciones de depuración, concretamente para el Run y Debug del VS Code.
- devcontainer.json -> construir y lanzar un docker preconfigurado con todas las dependencias necesarias.
## Activación
`ctrl + shift + p` en el VS Code para seleccionar el intérprete de python:

<img width="462" height="436" alt="image" src="https://github.com/user-attachments/assets/a074f67b-f356-482e-be58-ddedf769b130" />

Aquí, seleccionamos el gis:

<img width="451" height="149" alt="image" src="https://github.com/user-attachments/assets/1040e3c4-d4d8-4291-8f81-dc17dd97f0f6" />


## Verificación
Ejecutar el fichero `quick_env_check.py` de la carpeta src:

<img width="228" height="298" alt="image" src="https://github.com/user-attachments/assets/48f68eba-618d-4a2b-81c4-5bccd8a1cab7" />

Tenemos que tener el fichero `.env` en la raíz, al mismo nivel que el `README.md` y el `.gitignore`:

<img width="227" height="299" alt="image" src="https://github.com/user-attachments/assets/f3640506-5739-4bde-ab85-7e692a2fd21a" />

### Posibles errores
Si nos sale algo como lo siguiente al configurar VS Code:

<img width="2048" height="326" alt="image" src="https://github.com/user-attachments/assets/521defa7-ee0a-4a53-9d31-1fcc0b57bbea" />
Debemos ejecutar la isntrucción: 
 Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned 

Con esto permitimos scripts en nuestra sesión, pero sólo para nuestro usuario actual.
En caso de ser necesario, habrá que cerrar todas las terminales de VS Code y volver a abrir una nueva.
