// Página "En vivo": control de la cámara, estado, ajustes y últimas detecciones guardadas.
(function () {
  const R = window.RUTAS;
  const { pedir, pintarPildora } = window.Lince;
  const $ = (id) => document.getElementById(id);

  const video = $("video");
  const reposo = $("reposo");
  const btnCamara = $("btn-camara");
  const btnFoto = $("btn-foto");
  const ajDeteccion = $("aj-deteccion");
  const ajRegistro = $("aj-registro");
  const ajConfianza = $("aj-confianza");
  const ultimas = $("ultimas");

  let ultimo = null;          // último estado recibido del servidor
  let mostrando = false;      // el <img> tiene el flujo de video conectado
  let moviendoDeslizador = false;
  let vistos = null;          // ids de detecciones ya mostradas (null = primera carga)
  let ocupado = false;

  // ------------------------------------------------------------- video
  function conectarVideo() {
    if (mostrando) return;
    mostrando = true;
    video.src = R.video + "?t=" + Date.now(); // evita reutilizar un flujo anterior
    video.hidden = false;
    reposo.hidden = true;
  }

  function desconectarVideo(titulo, texto) {
    mostrando = false;
    video.removeAttribute("src");
    video.hidden = true;
    reposo.hidden = false;
    $("reposo-titulo").textContent = titulo || "La cámara está apagada";
    $("reposo-texto").textContent = texto || "Presiona «Encender cámara» para empezar.";
  }

  video.addEventListener("error", () => {
    if (mostrando) desconectarVideo("Se perdió la señal", "Vuelve a encender la cámara.");
  });

  // ----------------------------------------------------------- pintado
  function el(etiqueta, clase, texto) {
    const n = document.createElement(etiqueta);
    if (clase) n.className = clase;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  function mostrarError(nodo, texto) {
    nodo.hidden = !texto;
    nodo.textContent = texto || "";
  }

  function pintar(e) {
    ultimo = e;
    pintarPildora(e);
    const d = e.deteccion;
    const r = e.registro;

    const indicador = $("indicador");
    indicador.dataset.estado = e.activa ? (d.activa ? "viva" : "pausa") : "apagada";
    indicador.textContent = e.activa ? (d.activa ? "En vivo" : "Sin detección") : "Apagada";

    btnCamara.textContent = e.activa ? "Apagar cámara" : "Encender cámara";
    btnCamara.classList.toggle("boton-primario", !e.activa);
    btnFoto.setAttribute("aria-disabled", String(!e.activa));

    $("lec-fps").textContent = e.activa ? Math.round(e.fps) : 0;
    $("lec-det").textContent = d.fps ? d.fps.toFixed(1) : 0;
    $("lec-ms").textContent = d.inferencia_ms ? Math.round(d.inferencia_ms) : "-";
    $("lec-total").textContent = d.total;
    $("lec-modelo").textContent = d.modelo;
    $("lec-resolucion").textContent = e.resolucion;
    $("lec-espectadores").textContent = e.clientes;

    mostrarError($("error"), e.error);
    mostrarError($("det-error"), d.error || r.error);

    ajDeteccion.checked = d.activa;
    ajRegistro.checked = r.activo;
    ajRegistro.disabled = !r.disponible;
    if (!moviendoDeslizador) {
      ajConfianza.value = Math.round(d.confianza * 100);
      $("aj-confianza-valor").textContent = ajConfianza.value + "%";
    }

    $("alb-descubiertas").textContent = r.descubiertas;
    $("alb-barra").style.width = (r.descubiertas * 100 / r.total_clases) + "%";

    pintarObjetos(e);
    pintarUltimas(r.recientes);

    if (!e.activa && mostrando) desconectarVideo();
    if (e.activa && !mostrando) conectarVideo(); // la encendieron desde otra pestaña
  }

  function pintarObjetos(e) {
    const lista = $("escena");
    const d = e.deteccion;
    lista.replaceChildren();
    let vacio = "";
    if (!e.activa) vacio = "La cámara está apagada.";
    else if (!d.activa) vacio = "La detección está desactivada.";
    else if (!d.objetos.length) vacio = "No se detecta ningún objeto.";
    if (vacio) {
      lista.append(el("li", "vacio", vacio));
      return;
    }
    for (const o of d.objetos) {
      const li = el("li");
      const chip = el("span", "chip");
      chip.style.background = o.color;
      const medidor = el("span", "medidor");
      const relleno = el("span");
      relleno.style.width = Math.round(o.confianza * 100) + "%";
      medidor.append(relleno);
      li.append(chip, el("span", "nombre", o.nombre), el("span", "num", "×" + o.cantidad),
                medidor, el("span", "num", Math.round(o.confianza * 100) + "%"));
      lista.append(li);
    }
  }

  function pintarUltimas(recientes) {
    const nuevos = vistos === null ? [] : recientes.filter((a) => !vistos.has(a.id));
    vistos = new Set(recientes.map((a) => a.id));
    const firma = recientes.map((a) => a.id).join(",") || "vacia";
    if (firma === ultimas.dataset.firma) return; // nada cambió
    ultimas.dataset.firma = firma;

    ultimas.replaceChildren();
    if (!recientes.length) {
      ultimas.append(el("li", "vacio texto-suave", "Todavía no hay detecciones guardadas."));
      return;
    }
    const idsNuevos = new Set(nuevos.map((a) => a.id));
    for (const a of recientes.slice(0, 12)) {
      const li = el("li", idsNuevos.has(a.id) ? "reciente" : "");
      const enlace = el("a");
      enlace.href = R.bitacora + "?objeto=" + a.clase;
      const img = el("img");
      img.src = a.imagen;
      img.alt = a.nombre;
      img.loading = "lazy";
      enlace.append(img, el("span", "nombre", a.nombre + (a.cantidad > 1 ? " ×" + a.cantidad : "")),
                    el("span", "hora", a.hora + " · " + Math.round(a.confianza * 100) + "%"));
      li.append(enlace);
      ultimas.append(li);
    }
    const descubiertos = nuevos.filter((a) => a.nuevo);
    if (descubiertos.length) notificar(descubiertos);
  }

  // Aviso cuando aparece un tipo de objeto que nunca se había detectado
  let temporizadorAviso = null;
  function notificar(objetos) {
    const aviso = $("notificacion");
    aviso.replaceChildren("Nuevo objeto descubierto: ");
    objetos.forEach((a, i) => {
      if (i) aviso.append(", ");
      aviso.append(el("strong", "", a.nombre));  // en minúscula a mitad de la frase
    });
    aviso.hidden = false;
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(() => { aviso.hidden = true; }, 4000);
  }

  // ---------------------------------------------------------- acciones
  async function refrescar() {
    try { pintar(await pedir(R.estado)); } catch (_) {
      mostrarError($("error"), "Sin conexión con el servidor.");
    }
  }

  async function alternarCamara() {
    if (ocupado) return;
    ocupado = true;
    try {
      if (ultimo && ultimo.activa) {
        desconectarVideo();
        pintar(await pedir(R.detener, "POST"));
      } else {
        $("reposo-titulo").textContent = "Abriendo la cámara…";
        $("reposo-texto").textContent = "";
        const e = await pedir(R.iniciar, "POST");
        pintar(e);
        if (e.activa) conectarVideo();
        else desconectarVideo("No se pudo abrir la cámara", e.error);
      }
    } finally { ocupado = false; }
  }

  async function configurar(cambios) {
    try { pintar(await pedir(R.deteccion, "POST", cambios)); } catch (_) { /* el sondeo mostrará el error */ }
  }

  btnCamara.addEventListener("click", alternarCamara);
  btnFoto.addEventListener("click", (ev) => {
    if (btnFoto.getAttribute("aria-disabled") === "true") ev.preventDefault();
  });
  ajDeteccion.addEventListener("change", () => configurar({ activa: ajDeteccion.checked }));
  ajRegistro.addEventListener("change", () => configurar({ registrar: ajRegistro.checked }));

  let temporizador = null;
  ajConfianza.addEventListener("input", () => {
    moviendoDeslizador = true;
    $("aj-confianza-valor").textContent = ajConfianza.value + "%";
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      await configurar({ confianza: Number(ajConfianza.value) / 100 });
      moviendoDeslizador = false;
    }, 150);
  });

  // Atajos de teclado (no actúan mientras se usa un control)
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (ev.target.closest("input, textarea, select, button, a")) return;
    const tecla = ev.key.toLowerCase();
    if (tecla === " ") { ev.preventDefault(); alternarCamara(); }
    else if (tecla === "d") { ajDeteccion.click(); }
    else if (tecla === "f" && ultimo && ultimo.activa) { window.location.href = R.foto; }
  });

  refrescar();
  setInterval(refrescar, 700);
})();
