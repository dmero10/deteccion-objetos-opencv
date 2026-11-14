// Observatorio: control de la cámara, lecturas en vivo, ajustes, tira de avistamientos y sellos.
(function () {
  const R = window.RUTAS;
  const { pedir, pintarPildora } = window.Lince;
  const $ = (id) => document.getElementById(id);

  const visor = $("visor");
  const video = $("video");
  const reposo = $("reposo");
  const btnCamara = $("btn-camara");
  const btnFoto = $("btn-foto");
  const ajDeteccion = $("aj-deteccion");
  const ajRegistro = $("aj-registro");
  const ajConfianza = $("aj-confianza");
  const cinta = $("cinta");

  let ultimo = null;          // último estado recibido
  let mostrando = false;      // el <img> tiene el flujo conectado
  let moviendoRegla = false;
  let vistos = null;          // ids de avistamientos ya mostrados (null = primera carga)
  let ocupado = false;

  // ------------------------------------------------------------ video
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
    $("reposo-titulo").textContent = titulo || "La lente está cerrada.";
    $("reposo-texto").textContent = texto || "Enciende la cámara para empezar a observar.";
  }

  video.addEventListener("error", () => {
    if (mostrando) desconectarVideo("Se perdió la señal.", "Vuelve a encender la cámara para reintentar.");
  });

  // ---------------------------------------------------------- pintado
  function pintar(e) {
    ultimo = e;
    pintarPildora(e);
    const d = e.deteccion;
    const r = e.registro;

    visor.dataset.estado = e.activa ? (d.activa ? "viva" : "pausa") : "apagada";
    $("visor-resolucion").textContent = e.activa ? e.resolucion.replace("x", " × ") : "— × —";
    $("visor-rec-texto").textContent = e.activa ? (d.activa ? "Observando" : "Sin detección") : "Lente cerrada";

    btnCamara.classList.toggle("boton-peligro", e.activa);
    btnCamara.classList.toggle("boton-primario", !e.activa);
    $("btn-camara-texto").textContent = e.activa ? "Apagar cámara" : "Encender cámara";
    btnCamara.querySelector(".boton-icono").textContent = e.activa ? "■" : "●";
    btnFoto.setAttribute("aria-disabled", String(!e.activa));

    $("lec-fps").textContent = e.activa ? Math.round(e.fps) : 0;
    $("lec-det").textContent = d.fps ? d.fps.toFixed(1) : 0;
    $("lec-ms").textContent = d.inferencia_ms ? Math.round(d.inferencia_ms) : "—";
    $("lec-total").textContent = d.total;
    $("lec-modelo").textContent = d.modelo;
    $("lec-espectadores").textContent = e.clientes;

    mostrarError($("error"), e.error);
    mostrarError($("det-error"), d.error || r.error);

    ajDeteccion.checked = d.activa;
    ajRegistro.checked = r.activo;
    ajRegistro.disabled = !r.disponible;
    if (!moviendoRegla) {
      ajConfianza.value = Math.round(d.confianza * 100);
      $("aj-confianza-valor").textContent = ajConfianza.value + "%";
    }

    $("alb-descubiertas").textContent = r.descubiertas;
    $("alb-barra").style.width = (r.descubiertas * 100 / r.total_clases) + "%";

    pintarEscena(e);
    pintarCinta(r.recientes);

    if (!e.activa && mostrando) desconectarVideo();
    if (e.activa && !mostrando) conectarVideo(); // la encendieron desde otra pestaña
  }

  function mostrarError(nodo, texto) {
    nodo.hidden = !texto;
    nodo.textContent = texto || "";
  }

  function el(etiqueta, clase, texto) {
    const n = document.createElement(etiqueta);
    if (clase) n.className = clase;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  function pintarEscena(e) {
    const lista = $("escena");
    const d = e.deteccion;
    lista.replaceChildren();
    let vacio = "";
    if (!e.activa) vacio = "La cámara está apagada.";
    else if (!d.activa) vacio = "La detección está en pausa.";
    else if (!d.objetos.length) vacio = "Nada a la vista.";
    if (vacio) {
      lista.append(el("li", "escena-vacia", vacio));
      return;
    }
    for (const o of d.objetos) {
      const li = el("li", "escena-item");
      const chip = el("span", "chip");
      chip.style.background = o.color;
      const nombre = el("span", "escena-nombre", o.nombre);
      const cantidad = el("span", "escena-cantidad", "×" + o.cantidad);
      const barra = el("span", "medidor");
      const relleno = el("span");
      relleno.style.width = Math.round(o.confianza * 100) + "%";
      barra.append(relleno);
      const pct = el("span", "escena-pct", Math.round(o.confianza * 100) + "%");
      li.append(chip, nombre, cantidad, barra, pct);
      lista.append(li);
    }
  }

  function pintarCinta(recientes) {
    const nuevos = vistos === null ? [] : recientes.filter((a) => !vistos.has(a.id));
    vistos = new Set(recientes.map((a) => a.id));
    const firma = recientes.map((a) => a.id).join(",") || "vacia";
    if (firma === cinta.dataset.firma) return; // nada cambió: no redibujar
    cinta.dataset.firma = firma;

    cinta.replaceChildren();
    if (!recientes.length) {
      cinta.append(el("li", "cinta-vacia", "Aún no hay avistamientos. Cuando la cámara reconozca algo, quedará revelado aquí."));
      return;
    }
    const idsNuevos = new Set(nuevos.map((a) => a.id));
    for (const a of recientes) {
      const li = el("li", "fotograma" + (idsNuevos.has(a.id) ? " fotograma-nuevo" : ""));
      const enlace = el("a");
      enlace.href = R.bitacora + "?objeto=" + a.clase;
      const img = el("img");
      img.src = a.imagen;
      img.alt = a.nombre;
      img.loading = "lazy";
      const pie = el("span", "fotograma-pie");
      const nombre = el("span", "fotograma-nombre", a.nombre + (a.cantidad > 1 ? " ×" + a.cantidad : ""));
      const meta = el("span", "fotograma-meta", a.hora + " · " + Math.round(a.confianza * 100) + "%");
      pie.append(nombre, meta);
      enlace.append(img, pie);
      li.append(enlace);
      cinta.append(li);
    }
    for (const a of nuevos.filter((n) => n.nuevo).reverse()) sellar(a);
  }

  // ------------------------------------------------- sello de hallazgo
  const colaSellos = [];
  let selloVisible = false;

  function sellar(a) {
    colaSellos.push(a);
    if (!selloVisible) siguienteSello();
  }

  function siguienteSello() {
    const a = colaSellos.shift();
    const sello = $("sello");
    if (!a) { selloVisible = false; return; }
    selloVisible = true;
    $("sello-nombre").textContent = a.nombre;
    $("sello-pie").textContent = `Nº ${String(a.clase + 1).padStart(2, "0")} · ${ultimo ? ultimo.registro.descubiertas : "?"} de 80 en el álbum`;
    sello.hidden = false;
    sello.classList.remove("sello-sale");
    void sello.offsetWidth; // reinicia la animación
    sello.classList.add("sello-entra");
    setTimeout(() => {
      sello.classList.add("sello-sale");
      setTimeout(() => { sello.hidden = true; sello.classList.remove("sello-entra"); siguienteSello(); }, 450);
    }, 3800);
  }

  // -------------------------------------------------------- acciones
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
        $("reposo-titulo").textContent = "Abriendo la lente…";
        $("reposo-texto").textContent = "";
        const e = await pedir(R.iniciar, "POST");
        pintar(e);
        if (e.activa) conectarVideo();
        else desconectarVideo("No se pudo abrir la cámara.", e.error);
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
    moviendoRegla = true;
    $("aj-confianza-valor").textContent = ajConfianza.value + "%";
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      await configurar({ confianza: Number(ajConfianza.value) / 100 });
      moviendoRegla = false;
    }, 150);
  });

  // Atajos de teclado (no actúan mientras se escribe o se usa un control)
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (ev.target.closest("input, textarea, select, button, a, summary")) return;
    const tecla = ev.key.toLowerCase();
    if (tecla === " ") { ev.preventDefault(); alternarCamara(); }
    else if (tecla === "d") { ajDeteccion.click(); }
    else if (tecla === "g") { if (!ajRegistro.disabled) ajRegistro.click(); }
    else if (tecla === "f" && ultimo && ultimo.activa) { window.location.href = R.foto; }
  });

  refrescar();
  setInterval(refrescar, 700);
})();
