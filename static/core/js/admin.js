(() => {
  'use strict';
  function setup(root) {
    root.querySelectorAll('textarea[name="body"], textarea[name="answer"], textarea[name="about_text"], textarea[name$="-content"]').forEach(area => {
      if (area.dataset.toolbar || area.name.includes('__prefix__')) return;
      area.dataset.toolbar = 'ready';
      const toolbar = document.createElement('div');
      toolbar.className = 'content-toolbar';
      const actions = [
        ['Абзац', text => `\n\n${text}`],
        ['Список', text => '\n' + (text || 'Пункт списка').split('\n').map(line => line ? '- ' + line : '').join('\n') + '\n'],
        ['Подзаголовок', text => `\n\n## ${text || 'Подзаголовок'}\n\n`],
      ];
      actions.forEach(([label, format]) => {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = label;
        button.addEventListener('click', () => {
          const start = area.selectionStart, end = area.selectionEnd;
          area.setRangeText(format(area.value.slice(start, end)), start, end, 'select');
          area.dispatchEvent(new Event('input', {bubbles: true})); area.focus();
        });
        toolbar.append(button);
      });
      area.before(toolbar);
    });
    root.querySelectorAll('form[data-dirty-form], .change-form form[id$="_form"]').forEach(form => {
      if (form.dataset.dirtyReady) return;
      form.dataset.dirtyReady = '1';
      const changed = () => {
        form.dataset.dirty = '1';
        const note = form.querySelector('.owner-save-state');
        if (note) note.textContent = 'Есть несохранённые изменения.';
      };
      form.addEventListener('input', changed);
      form.addEventListener('change', changed);
      form.addEventListener('submit', () => { delete form.dataset.dirty; });
    });
    root.querySelectorAll('.inline-related:not(.empty-form)').forEach(inline => {
      if (inline.dataset.foldReady || !inline.querySelector('textarea')) return;
      inline.dataset.foldReady = '1';
      const heading = inline.querySelector('h3');
      if (!heading) return;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'owner-inline-toggle';
      const toggle = closed => {
        inline.classList.toggle('owner-inline-collapsed', closed);
        button.textContent = closed ? 'Развернуть текст' : 'Свернуть текст';
        button.setAttribute('aria-expanded', String(!closed));
      };
      button.addEventListener('click', () => toggle(!inline.classList.contains('owner-inline-collapsed')));
      heading.append(button);
      toggle(!inline.classList.contains('has_original') ? false : !inline.querySelector('.errorlist'));
    });
  }
  function sectionTabs() {
    const marker = document.querySelector('[data-section-tabs]');
    if (!marker) return;
    const form = marker.closest('form');
    const sections = [...form.querySelectorAll(':scope > div > fieldset.module')];
    if (sections.length < 2) return;
    const nav = document.createElement('div'); nav.className = 'owner-section-tabs';
    nav.setAttribute('role', 'tablist'); nav.setAttribute('aria-label', 'Настройки по разделам');
    const key = 'owner-section:' + location.pathname;
    const buttons = sections.map((section, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = section.querySelector('h2')?.textContent || `Раздел ${index + 1}`;
      button.id = `section-tab-${index}`; button.setAttribute('role', 'tab');
      section.id = `section-panel-${index}`; section.setAttribute('role', 'tabpanel');
      section.setAttribute('aria-labelledby', button.id); button.setAttribute('aria-controls', section.id);
      button.addEventListener('click', () => select(index)); nav.append(button); return button;
    });
    const select = index => {
      sections.forEach((section, at) => {
        section.hidden = at !== index;
        if (at === index) section.querySelectorAll(':scope > details').forEach(detail => { detail.open = true; });
        buttons[at].setAttribute('aria-selected', String(at === index));
        buttons[at].tabIndex = at === index ? 0 : -1;
      });
      try { sessionStorage.setItem(key, index); } catch (_) { /* Storage can be disabled. */ }
    };
    nav.addEventListener('keydown', event => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const current = buttons.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      select(next); buttons[next].focus();
    });
    marker.append(nav);
    let saved = 0;
    try { saved = Number(sessionStorage.getItem(key)) || 0; } catch (_) { /* Use the first section. */ }
    const invalid = sections.findIndex(section => section.querySelector('.errorlist'));
    select(invalid >= 0 ? invalid : Math.min(saved, sections.length - 1));
    form.addEventListener('invalid', event => {
      const index = sections.findIndex(section => section.contains(event.target));
      if (index >= 0) select(index);
    }, true);
  }
  function calendarDialog() {
    const dialog = document.getElementById('window-dialog');
    if (!dialog || !dialog.showModal) return;
    let opener;
    const close = () => {
      if (dialog.querySelector('[data-dirty="1"]') && !window.confirm('Закрыть без сохранения изменений?')) return;
      dialog.close(); opener?.focus();
    };
    dialog.querySelector('.dialog-close').addEventListener('click', close);
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('click', event => {
      if (event.target.closest('[data-close-panel]')) { event.preventDefault(); close(); }
    });
    document.querySelectorAll('[data-window-panel]').forEach(link => link.addEventListener('click', async event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); opener = link;
      const url = new URL(link.href); url.searchParams.set('panel', '1');
      try {
        const response = await fetch(url, {credentials: 'same-origin'});
        if (!response.ok || response.redirected) { location.href = link.href; return; }
        dialog.querySelector('.dialog-body').innerHTML = await response.text();
        setup(dialog); dialog.showModal();
      } catch (_) { location.href = link.href; }
    }));
  }
  function calendarDays() {
    const grid = document.querySelector('.calendar-grid');
    if (!grid) return;
    const days = [...grid.querySelectorAll('.calendar-day')];
    const nav = document.createElement('nav'); nav.className = 'calendar-day-tabs'; nav.setAttribute('aria-label', 'Дни недели');
    let selected = Math.max(0, days.findIndex(day => day.classList.contains('is-today')));
    const media = matchMedia('(max-width: 767px)');
    const buttons = days.map((day, index) => {
      const button = document.createElement('button'); button.type = 'button';
      button.textContent = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][index] + ' ' + day.querySelector('header strong').textContent.slice(0,2);
      button.setAttribute('aria-label', day.querySelector('header').textContent.trim());
      button.addEventListener('click', () => { selected = index; update(); });
      nav.append(button); return button;
    });
    const update = () => days.forEach((day, index) => {
      day.hidden = media.matches && index !== selected;
      buttons[index].setAttribute('aria-pressed', String(index === selected));
    });
    grid.before(nav); grid.classList.add('mobile-ready'); media.addEventListener('change', update); update();
  }
  document.addEventListener('DOMContentLoaded', () => {
    setup(document); sectionTabs(); calendarDialog(); calendarDays();
    document.querySelectorAll('.owner-nav a').forEach(link => {
      if (link.pathname.startsWith('/admin/') && link.pathname !== '/admin/' && location.pathname.startsWith(link.pathname)) link.setAttribute('aria-current', 'page');
    });
  });
  document.addEventListener('formset:added', event => setup(event.target));
  document.addEventListener('submit', event => {
    const message = event.target.dataset.confirm;
    if (message && !window.confirm(message)) event.preventDefault();
  });
  window.addEventListener('beforeunload', event => {
    const dirty = [...document.querySelectorAll('form[data-dirty="1"]')].some(form => {
      const dialog = form.closest('dialog'); return !dialog || dialog.open;
    });
    if (!dirty) return;
    event.preventDefault(); event.returnValue = '';
  });
})();
