// Utilidades comunes: indicador de cámara en la cabecera y peticiones con CSRF.
(function () {
  const pildora = document.getElementById("pildora");
  const pildoraTexto = document.getElementById("pildora-texto");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  function pintarPildora(e) {
    if (!pildora) return;
    let estado = "apagada";
    let texto = "Cámara apagada";
    if (e.activa) {
      estado = e.deteccion.activa ? "viva" : "pausa";
      texto = e.deteccion.activa ? `En vivo · ${Math.round(e.fps)} fps` : "Video sin detección";
    }
    pildora.dataset.estado = estado;
    pildoraTexto.textContent = texto;
  }

  async function pedir(url, metodo, cuerpo) {
    const opciones = { method: metodo || "GET", headers: {} };
    if (metodo === "POST") opciones.headers["X-CSRFToken"] = csrf;
    if (cuerpo !== undefined) {
      opciones.headers["Content-Type"] = "application/json";
      opciones.body = JSON.stringify(cuerpo);
    }
    const r = await fetch(url, opciones);
    return r.json();
  }

  window.Lince = { pintarPildora, pedir };

  // En las demás páginas el indicador se actualiza solo; el observatorio lo hace él mismo.
  if (!document.body.classList.contains("pagina-observatorio")) {
    const refrescar = () => pedir(window.LINCE.estado).then(pintarPildora).catch(() => {});
    refrescar();
    setInterval(refrescar, 3000);
  }
})();
