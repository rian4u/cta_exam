(function () {
  const STORAGE_KEY = "taxDoldolSkin";
  const SKINS = [1, 2, 3];

  function normalizeSkin(value) {
    const parsed = Number(value);
    if (SKINS.includes(parsed)) {
      return parsed;
    }
    return 1;
  }

  function readSkin() {
    try {
      return normalizeSkin(localStorage.getItem(STORAGE_KEY));
    } catch (_) {
      return 1;
    }
  }

  function writeSkin(value) {
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch (_) {}
  }

  function applySkin(value) {
    const skin = normalizeSkin(value);
    document.body.classList.remove("skin-1", "skin-2", "skin-3");
    document.body.classList.add(`skin-${skin}`);
    document.querySelectorAll(".skin-label").forEach((el) => {
      el.textContent = `스킨 ${skin}`;
    });
    return skin;
  }

  function shiftSkin(current, delta) {
    const index = SKINS.indexOf(current);
    const nextIndex = (index + delta + SKINS.length) % SKINS.length;
    return SKINS[nextIndex];
  }

  function initSkinControls() {
    let currentSkin = applySkin(readSkin());

    document.querySelectorAll(".skin-prev").forEach((button) => {
      button.addEventListener("click", () => {
        currentSkin = shiftSkin(currentSkin, -1);
        writeSkin(currentSkin);
        applySkin(currentSkin);
      });
    });

    document.querySelectorAll(".skin-next").forEach((button) => {
      button.addEventListener("click", () => {
        currentSkin = shiftSkin(currentSkin, 1);
        writeSkin(currentSkin);
        applySkin(currentSkin);
      });
    });

    window.addEventListener("storage", (event) => {
      if (event.key === STORAGE_KEY) {
        currentSkin = applySkin(readSkin());
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSkinControls);
  } else {
    initSkinControls();
  }
})();
