(function () {
  "use strict";

  const NOISE_ICONS = {
    transparency: `
      <svg viewBox="0 0 28 28" width="24" height="24" fill="currentColor">
        <circle cx="14" cy="14.2" r="3.4" />
        <path d="M8.4 21.8c0-2.7 2.5-4.3 5.6-4.3s5.6 1.6 5.6 4.3c0 .6-.4 1-1 1H9.4c-.6 0-1-.4-1-1z" />
        <circle cx="14" cy="6.2" r="1.1" />
        <circle cx="9.6" cy="7.5" r="1.1" />
        <circle cx="18.4" cy="7.5" r="1.1" />
        <circle cx="6.8" cy="11.1" r="1.1" />
        <circle cx="21.2" cy="11.1" r="1.1" />
        <circle cx="6.4" cy="15.4" r="1.05" />
        <circle cx="21.6" cy="15.4" r="1.05" />
      </svg>
    `,
    anc: `
      <svg viewBox="0 0 28 28" width="24" height="24" fill="currentColor">
        <path d="M6.4 16.5a7.6 7.6 0 1 1 15.2 0" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
        <circle cx="14" cy="14.2" r="3.4" />
        <path d="M8.4 21.8c0-2.7 2.5-4.3 5.6-4.3s5.6 1.6 5.6 4.3c0 .6-.4 1-1 1H9.4c-.6 0-1-.4-1-1z" />
      </svg>
    `,
    off: `
      <svg viewBox="0 0 28 28" width="24" height="24" fill="currentColor">
        <circle cx="14" cy="14.2" r="3.5" />
        <path d="M8.2 21.8c0-2.7 2.6-4.4 5.8-4.4s5.8 1.7 5.8 4.4c0 .6-.4 1-1 1H9.2c-.6 0-1-.4-1-1z" />
      </svg>
    `,
  };

  const SLIDER_ICONS = {
    ancLight: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6.8 11.4a5.8 5.8 0 0 1 10.4 0" />
        <path d="M12 10.2a3.3 3.3 0 0 0-3.3 3.3c0 1.4.8 2.4 1.9 2.9v3.2c0 .6.5 1.1 1.1 1.1h.6c.6 0 1.1-.5 1.1-1.1v-3.2c1.1-.5 1.9-1.5 1.9-2.9a3.3 3.3 0 0 0-3.3-3.3z" />
      </svg>
    `,
    ancDeep: `
      <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4.2 11a8.8 8.8 0 0 1 15.6 0" />
        <path d="M6.6 12.2a6.2 6.2 0 0 1 10.8 0" />
        <path d="M8.9 13.4a3.6 3.6 0 0 1 6.2 0" />
        <path d="M12 11.6a3 3 0 0 0-3 3c0 1.3.7 2.2 1.7 2.6v2.7c0 .6.4 1 1 1h.6c.6 0 1-.4 1-1v-2.7c1-.4 1.7-1.3 1.7-2.6a3 3 0 0 0-3-3z" />
      </svg>
    `,
    transSmall: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6.5 9.8a4.2 4.2 0 0 1 8.1-1.3c.8 1.7.1 3.4-1.2 4.6-.8.7-1.3 1.4-1.3 2.4a1.8 1.8 0 0 1-3.5.5" />
        <path d="M9.8 10.2a1.7 1.7 0 0 1 2.2 1.7c0 .8-.5 1.4-1 1.8" />
        <path d="M17.5 9.6a3.5 3.5 0 0 1 0 4.8" />
      </svg>
    `,
    transLarge: `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 9.8a4.2 4.2 0 0 1 8.1-1.3c.8 1.7.1 3.4-1.2 4.6-.8.7-1.3 1.4-1.3 2.4a1.8 1.8 0 0 1-3.5.5" />
        <path d="M8.3 10.2a1.7 1.7 0 0 1 2.2 1.7c0 .8-.5 1.4-1 1.8" />
        <path d="M16 9.3a4 4 0 0 1 0 5.4" />
        <path d="M18.6 7.4a6.8 6.8 0 0 1 0 9.2" />
      </svg>
    `,
  };

  const MENU_ICONS = {
    gestures: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M11.6 4.2a1.45 1.45 0 0 0-1.45 1.45v5.65l-.72-.52a1.42 1.42 0 0 0-1.98.33 1.38 1.38 0 0 0 .25 1.88l3.18 3.23c.68.68 1.6 1.08 2.57 1.08h2.65a3.2 3.2 0 0 0 3.2-3.2v-3.55a1.25 1.25 0 0 0-2.2-.82 1.25 1.25 0 0 0-2.05-.6 1.25 1.25 0 0 0-2.0-.42V5.65A1.45 1.45 0 0 0 11.6 4.2z"/>
      </svg>
    `,
    "audio-effects": `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor">
        <path d="M5 9.5v5c0 .55.45 1 1 1h3.2l4.4 3.45c.66.52 1.6.05 1.6-.79V5.84c0-.84-.94-1.31-1.6-.79L9.2 8.5H6c-.55 0-1 .45-1 1z"/>
        <path d="M17.5 8.8a4.5 4.5 0 0 1 0 6.4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
      </svg>
    `,
    "additional-settings": `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor">
        <path fill-rule="evenodd" d="M10.76 4.4a2.4 2.4 0 0 1 2.48 0l5.02 2.9a2.4 2.4 0 0 1 1.24 2.1v5.2a2.4 2.4 0 0 1-1.24 2.1l-5.02 2.9a2.4 2.4 0 0 1-2.48 0l-5.02-2.9A2.4 2.4 0 0 1 4.5 14.6V9.4a2.4 2.4 0 0 1 1.24-2.1l5.02-2.9zM12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z"/>
      </svg>
    `,
    "find-earphones": `
      <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-linecap="round">
        <path d="M5.2 8.2a6.2 6.2 0 0 0 0 7.6" stroke-width="1.6"/>
        <path d="M7.3 9.9a3.6 3.6 0 0 0 0 4.2" stroke-width="1.6"/>
        <path d="M18.8 8.2a6.2 6.2 0 0 1 0 7.6" stroke-width="1.6"/>
        <path d="M16.7 9.9a3.6 3.6 0 0 1 0 4.2" stroke-width="1.6"/>
        <path fill="currentColor" stroke="none" d="M12.2 6.6c-1.7 0-2.9 1.2-2.9 2.8 0 1.2.6 2.1 1.5 2.5v4.9a1.2 1.2 0 0 0 2.4 0v-4.9c1.1-.4 1.9-1.3 1.9-2.5 0-1.6-1.2-2.8-2.9-2.8z"/>
      </svg>
    `,
    "update-firmware": `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path fill-rule="evenodd" d="M7.2 17.5h9.9a3.4 3.4 0 0 0 .5-6.76 4.8 4.8 0 0 0-9.22-1.46A3.7 3.7 0 0 0 7.2 17.5zm4.8-1.95l2.75-2.75h-1.85V9.9h-1.8v2.9H9.25L12 15.55z"/>
      </svg>
    `,
    "about-device": `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor">
        <path fill-rule="evenodd" d="M7 4.8h10a2.2 2.2 0 0 1 2.2 2.2v10a2.2 2.2 0 0 1-2.2 2.2H7A2.2 2.2 0 0 1 4.8 17V7A2.2 2.2 0 0 1 7 4.8zm2 4.6a.9.9 0 0 0 0 1.8h6a.9.9 0 1 0 0-1.8H9zm0 3.7a.9.9 0 0 0 0 1.8h3.8a.9.9 0 1 0 0-1.8H9z"/>
      </svg>
    `,
    faq: `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor">
        <path d="M20.3 4.4c.5-.2 1 .3.8.8l-4.2 14.3c-.2.6-.9.7-1.3.2l-3.9-4.5-3.1 2.1c-.4.3-.9 0-.9-.5v-3.5L17.4 6.5 6.8 12.1 3.7 10.6c-.5-.2-.5-.9 0-1.1L20.3 4.4z"/>
      </svg>
    `,
    "about-earphones": `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor">
        <path fill-rule="evenodd" d="M12 4.2a7.8 7.8 0 1 0 0 15.6 7.8 7.8 0 0 0 0-15.6zm0 3.4a1.05 1.05 0 1 1 0 2.1 1.05 1.05 0 0 1 0-2.1zm-1 3.8a1 1 0 0 1 2 0v4.4a1 1 0 0 1-2 0v-4.4z"/>
      </svg>
    `,
    bluetooth: `
      <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6.5 6.5 17.5 17.5 12 22 12 2 17.5 6.5 6.5 17.5"></polyline>
      </svg>
    `,
  };

  const UI_ICONS = {
    backArrow: `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <line x1="19" y1="12" x2="5" y2="12"></line>
        <polyline points="11 18 5 12 11 6"></polyline>
      </svg>
    `,
    chevronRight: `
      <svg viewBox="0 0 12 18" width="8" height="13" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 3 9 9 3 15"></polyline>
      </svg>
    `,
    upDownChevrons: `
      <svg viewBox="0 0 14 20" width="11" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 7 7 3 11 7"></polyline>
        <polyline points="3 13 7 17 11 13"></polyline>
      </svg>
    `,
    checkMark: `
      <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 10.5 8.2 14.5 16 6"></polyline>
      </svg>
    `,
  };

  function batterySvg(percent, charging, isLight) {
    const emptyStroke = isLight ? "#9A9AA4" : "#5A5A60";
    const activeStroke = isLight ? "#6E6E78" : "#9A9A9E";
    if (percent === null || percent === undefined || Number.isNaN(Number(percent))) {
      return `
        <svg viewBox="0 0 24 13" width="22" height="12" aria-hidden="true">
          <rect x="0.9" y="1.1" width="18.5" height="10.8" rx="2.6" fill="none" stroke="${emptyStroke}" stroke-width="1.4" />
          <path d="M21 4.2v4.6a1.1 1.1 0 0 0 1.2-1.1V5.3A1.1 1.1 0 0 0 21 4.2z" fill="${emptyStroke}" />
        </svg>
      `;
    }
    const pct = Math.max(0, Math.min(100, Number(percent)));
    const fillW = Math.max(1.5, (pct / 100) * 14.5);
    const fillColor = pct <= 15 ? "#E5484D" : "#18B26B";
    return `
      <svg viewBox="0 0 24 13" width="22" height="12" aria-hidden="true">
        <rect x="0.9" y="1.1" width="18.5" height="10.8" rx="2.6" fill="none" stroke="${activeStroke}" stroke-width="1.4" />
        <rect x="2.9" y="3.1" width="${fillW.toFixed(1)}" height="6.8" rx="1.2" fill="${fillColor}" />
        <path d="M21 4.2v4.6a1.1 1.1 0 0 0 1.2-1.1V5.3A1.1 1.1 0 0 0 21 4.2z" fill="${activeStroke}" />
        ${charging ? '<path d="M10.8 2.6L8.2 6.8h2.1l-.7 3.6 2.8-4.3h-2.1l.5-3.5z" fill="#FFFFFF" />' : ""}
      </svg>
    `;
  }

  window.XiaomiIcons = {
    NOISE_ICONS,
    SLIDER_ICONS,
    MENU_ICONS,
    UI_ICONS,
    batterySvg,
  };
})();
