/* CiteVahti panel — document-level event delegation + the action registry.
 *
 * Components register their [data-act] handlers via registerActions({ act: fn }), so the
 * mapping lives with the component that owns it instead of in one central object. This
 * file keeps a SINGLE delegated click listener (one closest()-chain) as the dispatch point.
 * Handlers receive (el, event) — el is the matched [data-act] element.
 *
 * Classic script, loaded before app.js (which populates the registry at parse time). The
 * non-act branches and every handler reference functions defined in app.js / component
 * files; those resolve at click time, not at parse. The copy/change/keydown listeners
 * migrate here as their owning components are extracted. */

const _actions = {};
function registerActions(map) { Object.assign(_actions, map); }

document.addEventListener("click", (e) => {
  // Match only the nav tabs — NOT the #split container, which also carries a
  // data-surface attribute (for CSS), and would otherwise swallow every workspace click.
  const nv = e.target.closest(".surfnav-tab"); if (nv) { stopAwaitingClaims(); return void renderSurface(nv.dataset.surface); }
  const qq = e.target.closest("[data-queue]"); if (qq) { state.queueAll = qq.dataset.queue === "all"; return void renderQueue(); }
  const sw = e.target.closest("[data-switch]"); if (sw) return switchRoot(sw.dataset.switch);
  const cn = e.target.closest("[data-connect]"); if (cn) return void connect(cn.dataset.connect);
  if (e.target.closest("[data-connect-close]")) return void closeConnectModal();
  if (e.target.closest("[data-export-close]")) return void closeExportModal();
  if (e.target.closest("[data-import-close]")) return void closeImportModal();
  if (e.target.closest("[data-import-save]")) return void saveImported();
  if (e.target.closest("[data-import-prompt]")) return void copyClaimTestsPrompt();
  const cs = e.target.closest("[data-connect-submit]"); if (cs) return void submitConnect(cs.dataset.connectSubmit);
  const ms = e.target.closest("[data-ms]"); if (ms) return void loadManuscript(ms.dataset.ms).then(renderMsBar);
  if (e.target.id === "bindBtn") return void bindFolder();
  if (e.target.closest("#browseBtn") || e.target.closest("#reconOpen")) return void openBrowse(($("#bindDir") || {}).value || state.ctx.manuscripts_dir);
  const bn = e.target.closest("[data-browse]"); if (bn) return void openBrowse(bn.dataset.browse);
  const bu = e.target.closest("[data-browse-use]"); if (bu) return void useBrowseFolder(bu.dataset.browseUse);
  if (e.target.closest("[data-browse-close]")) return void closeBrowse();
  if (e.target.closest("[data-test-close]")) return void closeTests();
  if (e.target.closest("[data-test-online]")) return void runTests(true);
  const tf = e.target.closest("[data-test-focus]"); if (tf) { closeTests(); return void selectClaim(tf.dataset.testFocus); }
  if (e.target.closest("[data-wh-close]")) return void closeWarehouse();
  const wh = e.target.closest("[data-wh]"); if (wh) return void whAction(wh.dataset.wh);
  if (e.target.closest("[data-ai-close]")) return void closeAiSettings();
  if (e.target.id === "pasteSave") return void savePastedManuscript();
  if (e.target.id === "screenTopicBtn") return void copyScreenTopicPrompt();
  if (e.target.id === "addClaim") return void toggleAddClaim();
  const sp = e.target.closest("[data-claim]"); if (sp) return void selectClaim(sp.dataset.claim);
  const cp = e.target.closest("[data-cand]"); if (cp) { state.candIdx = +cp.dataset.cand; resetWrite(); return renderCard(); }
  const rb = e.target.closest("[data-rate]"); if (rb) return void rate(rb.dataset.rate);
  const dc = e.target.closest("[data-decide]"); if (dc) return void recordDecision(dc.dataset.decide);
  const lk = e.target.closest("[data-link]"); if (lk) return void linkRecord(lk.dataset.link);
  const zs = e.target.closest("[data-zsave]"); if (zs) return void zsave(zs.dataset.zsave, zs);
  const act = e.target.closest("[data-act]"); if (act) (_actions[act.dataset.act] || (() => {}))(act, e);
});

/* Keyboard. The universal parts live here — the modal Escape/Tab focus-trap, the input
 * guard, and Enter/Space activation of a focused claim span. The review/navigation keys
 * (j/k, 1–7, o/r/d, s/a, ↵, ? , u) are owned by the card and registered via registerKeys();
 * each handler returns true once it handles the event. */
const _keyHandlers = [];
function registerKeys(fn) { _keyHandlers.push(fn); }
document.addEventListener("keydown", (e) => {
  // modal-first: Escape dismisses the open dialog; Tab is trapped inside it
  const openModal = document.querySelector(".modal");
  if (openModal) {
    if (e.key === "Escape") {
      const close = { whModal: closeWarehouse, aiModal: closeAiSettings,
                      browseModal: closeBrowse, testModal: closeTests,
                      connectModal: closeConnectModal, exportModal: closeExportModal,
                      importModal: closeImportModal }[openModal.id];
      (close || (() => closeModalEl(openModal)))();
      return e.preventDefault();
    }
    if (e.key === "Tab") {
      const f = [...openModal.querySelectorAll(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
        .filter((el) => !el.disabled && el.offsetParent !== null);
      if (f.length) {
        const first = f[0], last = f[f.length - 1];
        if (document.activeElement === openModal) { first.focus(); return e.preventDefault(); }
        if (e.shiftKey && document.activeElement === first) { last.focus(); return e.preventDefault(); }
        if (!e.shiftKey && document.activeElement === last) { first.focus(); return e.preventDefault(); }
      }
    }
  }
  // guard non-Element targets (e.matches absent) so synthetic/dispatched events never throw
  if (e.target.matches && e.target.matches("input, textarea, select")) return;
  // a focused claim span is role="button": Enter/Space must activate it (intrinsic button
  // behaviour for keyboard users — works even when shortcuts are turned off).
  const focusedClaim = e.target.closest && e.target.closest("[data-claim]");
  if (focusedClaim && (e.key === "Enter" || e.key === " ")) {
    selectClaim(focusedClaim.dataset.claim); return e.preventDefault();
  }
  if (state.hotkeysOff) return;                          // user turned shortcuts off (writing mode)
  for (const h of _keyHandlers) { if (h(e)) return; }    // component-owned keys (card etc.)
});
