document.addEventListener('DOMContentLoaded', () => {
    const splash = document.getElementById('splash-screen');

    // Comprobar si ya se mostró en esta sesión de navegador
    if (!sessionStorage.getItem('splashShown')) {
        // Duración de la animación (3.5 segundos)
        setTimeout(() => {
            splash.classList.add('splash-hidden');
            // Guardamos en la sesión para que no vuelva a salir al navegar
            sessionStorage.setItem('splashShown', 'true');
        }, 3500);
    } else {
        // Si ya se mostró, eliminamos el div inmediatamente para no estorbar
        if (splash) {
            splash.style.display = 'none';
        }
    }
});