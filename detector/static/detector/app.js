// Controles de la cámara y panel de estado.
(function () {
  const R = window.RUTAS;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  const video = document.getElementById("video");
  const aviso = document.getElementById("aviso");
  const avisoTexto = document.getElementById("aviso-texto");
  const indicador = document.getElementById("indicador");
  const btnIniciar = document.getElementById("btn-iniciar");
  const btnDetener = document.getElementById("btn-detener");
  const btnFoto = document.getElementById("btn-foto");
  const error = document.getElementById("error");
  const dato = (id) => document.getElementById("dato-" + id);

  let mostrando = false;

  function mostrarVideo() {
    if (mostrando) return;
    mostrando = true;
    // El parámetro evita que el navegador reutilice un flujo anterior en caché
    video.src = R.video + "?t=" + Date.now();
    video.hidden = false;
    aviso.hidden = true;
  }

  function ocultarVideo(mensaje) {
    mostrando = false;
    video.removeAttribute("src");
    video.hidden = true;
    aviso.hidden = false;
    avisoTexto.innerHTML = mensaje ||
      "La cámara está apagada. Presiona <strong>Iniciar</strong> para ver el video.";
  }

  function pintarEstado(e) {
    indicador.textContent = e.activa ? "En vivo" : "Apagada";
    indicador.className = "indicador " + (e.activa ? "encendido" : "apagado");
    dato("estado").textContent = e.activa ? "Activa" : "Apagada";
    dato("fps").textContent = e.fps;
    dato("resolucion").textContent = e.resolucion;
    dato("indice").textContent = e.indice;
    dato("clientes").textContent = e.clientes;

    btnIniciar.disabled = e.activa;
    btnDetener.disabled = !e.activa;
    btnFoto.setAttribute("aria-disabled", String(!e.activa));

    error.hidden = !e.error;
    error.textContent = e.error || "";

    if (!e.activa && mostrando) ocultarVideo();
  }

  async function pedir(url, metodo) {
    const opciones = { method: metodo || "GET", headers: {} };
    if (metodo === "POST") opciones.headers["X-CSRFToken"] = csrf;
    const r = await fetch(url, opciones);
    return r.json();
  }

  async function refrescar() {
    try {
      pintarEstado(await pedir(R.estado));
    } catch (_) {
      error.hidden = false;
      error.textContent = "No hay conexión con el servidor.";
    }
  }

  btnIniciar.addEventListener("click", async () => {
    btnIniciar.disabled = true;
    avisoTexto.textContent = "Abriendo la cámara…";
    const e = await pedir(R.iniciar, "POST");
    pintarEstado(e);
    if (e.activa) mostrarVideo();
    else ocultarVideo("No se pudo abrir la cámara.");
  });

  btnDetener.addEventListener("click", async () => {
    btnDetener.disabled = true;
    ocultarVideo();
    pintarEstado(await pedir(R.detener, "POST"));
  });

  btnFoto.addEventListener("click", (ev) => {
    if (btnFoto.getAttribute("aria-disabled") === "true") ev.preventDefault();
  });

  video.addEventListener("error", () => {
    if (mostrando) ocultarVideo("Se perdió la transmisión. Presiona <strong>Iniciar</strong> para reintentar.");
  });

  // Al cargar: si la cámara ya estaba encendida (otra pestaña), mostrar el video.
  pedir(R.estado).then((e) => {
    pintarEstado(e);
    if (e.activa) mostrarVideo();
  }).catch(refrescar);

  setInterval(refrescar, 1000);
})();
