/**
 * Auto-dismiss para mensajes flash
 * Los mensajes desaparecen automáticamente después de 7 segundos
 */

document.addEventListener('DOMContentLoaded', function() {
    // Seleccionar todas las alertas
    const alerts = document.querySelectorAll('.alert-dismissible');
    
    alerts.forEach(function(alert) {
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



document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[type="password"]').forEach(function(input) {
        // Envolver en input-group si no está ya
        const parent = input.parentElement;
        if (!parent.classList.contains('input-group')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'input-group';
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
        }

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline-secondary';
        btn.tabIndex = -1;
        btn.innerHTML = '<i class="bi bi-eye"></i>';

        btn.addEventListener('click', function() {
            const icon = btn.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.replace('bi-eye', 'bi-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.replace('bi-eye-slash', 'bi-eye');
            }
        });

        input.parentElement.appendChild(btn);
    });
});