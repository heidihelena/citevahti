/* CiteVahti panel — modal lifecycle. Every overlay goes through modalShell()/closeModalEl()
 * so it announces as a dialog, moves focus inside on open, and restores it on close. Escape +
 * a Tab focus-trap live in the global keydown listener. Classic script; loads before app.js.
 * leaveModal() calls renderSurface() (defined in app.js) — resolved at click time, not parse. */

let _modalReturnFocus = null;

/* modalShell(id) builds a centered .modal overlay (default). modalShell(id, host)
 * instead mounts the same content inline inside a surface container — no backdrop,
 * no focus-trap — so the modal render functions can be reused verbatim on a surface.
 * The box keeps its id either way, so the functions' re-render targets ($("#whModal")
 * etc.) resolve in both modes. */
function modalShell(id, host) {
  let box = document.getElementById(id);
  if (!box) {
    box = document.createElement("div");
    box.id = id;
    box.tabIndex = -1;
  }
  if (host) {
    box.className = "surface-host";
    if (box.parentElement !== host) host.appendChild(box);
  } else {
    box.className = "modal";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    if (box.parentElement !== document.body) document.body.appendChild(box);
    _modalReturnFocus = document.activeElement;          // restore on close
    setTimeout(() => { try { box.focus(); } catch {} }, 0);
  }
  return box;
}
function closeModalEl(box) {
  if (!box) return;
  box.remove();
  const back = _modalReturnFocus; _modalReturnFocus = null;
  if (back && back.focus) { try { back.focus(); } catch {} }
}
/* A modal's ✕/Done acts as "leave": inside a surface it routes back to the review
 * workspace (the surface stays mounted, just hidden); as a real modal it's removed. */
function leaveModal(id, cleanup) {
  if (cleanup) cleanup();
  const box = document.getElementById(id);
  if (box && box.closest(".surface")) return void renderSurface("workspace");
  closeModalEl(box);
}
