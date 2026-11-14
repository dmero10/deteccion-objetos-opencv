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

  const detActiva = document.getElementById("det-activa");
  const detConfianza = document.getElementById("det-confianza");
  const detConfianzaValor = document.getElementById("det-confianza-valor");
  const detTotal = document.getElementById("det-total");
  const detMs = document.getElementById("det-ms");
  const detFps = document.getElementById("det-fps");
  const detModelo = document.getElementById("det-modelo");
  const detError = document.getElementById("det-error");
  const detLista = document.getElementById("det-lista");

  let mostrando = false;
  let moviendoDeslizador = false;

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

    pintarDeteccion(e);

    if (!e.activa && mostrando) ocultarVideo();
  }

  function pintarDeteccion(e) {
    const d = e.deteccion;
    detActiva.checked = d.activa;
    if (!moviendoDeslizador) {
      detConfianza.value = Math.round(d.confianza * 100);
      detConfianzaValor.textContent = detConfianza.value + "%";
    }
    detTotal.textContent = d.total;
    detMs.textContent = d.inferencia_ms > 0 ? d.inferencia_ms + " ms" : "-";
    detFps.textContent = d.fps > 0 ? d.fps : "-";
    detModelo.textContent = d.modelo;
    detError.hidden = !d.error;
    detError.textContent = d.error || "";

    let aviso = "";
    if (!e.activa) aviso = "Inicia la cámara para ver los objetos detectados.";
    else if (!d.activa) aviso = "La detección está desactivada.";
    else if (d.objetos.length === 0) aviso = "No se detecta ningún objeto.";

    detLista.replaceChildren();
    if (aviso) {
      const li = document.createElement("li");
      li.className = "vacio";
      li.textContent = aviso;
      detLista.append(li);
      return;
    }
    for (const o of d.objetos) {
      const li = document.createElement("li");
      const punto = document.createElement("span");
      punto.className = "punto";
      punto.style.background = o.color;
      const nombre = document.createElement("span");
      nombre.className = "nombre";
      nombre.textContent = o.nombre;
      const cantidad = document.createElement("span");
      cantidad.className = "cantidad";
      cantidad.textContent = "×" + o.cantidad;
      const conf = document.createElement("span");
      conf.className = "conf";
      conf.textContent = Math.round(o.confianza * 100) + "%";
      li.append(punto, nombre, cantidad, conf);
      detLista.append(li);
    }
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

  async function configurarDeteccion(cambios) {
    try {
      pintarEstado(await pedir(R.deteccion, "POST", cambios));
    } catch (_) { /* el sondeo periódico mostrará el error */ }
  }

  detActiva.addEventListener("change", () => configurarDeteccion({ activa: detActiva.checked }));

  let temporizador = null;
  detConfianza.addEventListener("input", () => {
    moviendoDeslizador = true;
    detConfianzaValor.textContent = detConfianza.value + "%";
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      await configurarDeteccion({ confianza: Number(detConfianza.value) / 100 });
      moviendoDeslizador = false;
    }, 150);
  });

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

  setInterval(refrescar, 700);
})();
