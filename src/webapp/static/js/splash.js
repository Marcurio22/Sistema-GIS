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

// --- Lógica de Cierre de Sesión ---
document.addEventListener('DOMContentLoaded', () => {
    // Buscamos el enlace de logout (usando el selector de clase que tienes en base.html)
    const logoutBtn = document.querySelector('a[href*="logout"]');
    const logoutOverlay = document.getElementById('logout-overlay');

    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            // 1. Evitar que el navegador cierre sesión inmediatamente
            e.preventDefault();
            const logoutUrl = this.href;

            // 2. Mostrar la animación (la marea sube)
            logoutOverlay.classList.add('show');

            // 3. Esperar 2 segundos y redirigir
            setTimeout(() => {
                // Limpiamos el sessionStorage para que al volver a entrar vea el splash de nuevo
                sessionStorage.removeItem('splashShown');
                window.location.href = logoutUrl;
            }, 2000);
        });
    }
});