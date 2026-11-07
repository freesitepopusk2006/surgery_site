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
  }
  document.addEventListener('DOMContentLoaded', () => setup(document));
  document.addEventListener('formset:added', event => setup(event.target));
})();
