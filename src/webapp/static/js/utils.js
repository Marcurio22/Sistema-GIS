/**
 * Auto-dismiss para mensajes flash
 * Los mensajes desaparecen automáticamente después de 7 segundos
 */

document.addEventListener('DOMContentLoaded', function() {
    // Seleccionar todas las alertas
    const alerts = document.querySelectorAll('.alert-dismissible');
    
    alerts.forEach(function(alert) {
        // Auto-dismiss después de 7 segundos (7000ms)
        setTimeout(function() {
            // Agregar clase fade-out para animación suave
            alert.classList.remove('show');
            
            // Esperar a que termine la animación antes de remover del DOM
            setTimeout(function() {
                alert.remove();
            }, 150); // Duración de la animación fade de Bootstrap
        }, 5000);
    });
});