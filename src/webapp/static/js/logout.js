document.addEventListener('DOMContentLoaded', () => {
  const logoutBtn = document.getElementById('logout-link');
  const logoutOverlay = document.getElementById('logout-overlay');

  // Si falta alguno, no hacemos nada (evita romper la navegación)
  if (!logoutBtn || !logoutOverlay) return;

  logoutBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const logoutUrl = logoutBtn.href;

    logoutOverlay.classList.add('show');

    setTimeout(() => {
      sessionStorage.removeItem('splashShown');
      window.location.href = logoutUrl;
    }, 2000);
  });
});
