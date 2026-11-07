(() => {
  'use strict';
  const normalize = value => value.toLocaleLowerCase('ru').normalize('NFKC').replaceAll('ё', 'е').trim();
  const debounce = (fn, delay = 160) => {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
  };
  const plural = (count, forms) => {
    const rule = new Intl.PluralRules('ru').select(count);
    return forms[rule] || forms.other;
  };

  const menu = document.getElementById('mobileMenu');
  const toggle = document.getElementById('menuToggle');
  function closeMenu() {
    if (!menu || !toggle) return;
    menu.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Открыть меню');
  }
  toggle?.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    menu.hidden = !open;
  });
  menu?.addEventListener('click', event => {
    if (event.target.closest('a, [data-booking-open]')) closeMenu();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle?.getAttribute('aria-expanded') === 'true') {
      closeMenu(); toggle.focus();
    }
  });
  window.matchMedia('(min-width: 961px)').addEventListener('change', event => {
    if (event.matches) closeMenu();
  });

  const dialog = document.getElementById('bookingDialog');
  const form = document.getElementById('bookingForm');
  const formWrap = document.getElementById('bookingFormWrap');
  const success = document.getElementById('bookingSuccess');
  const formError = document.getElementById('bookingError');
  let returnFocus;
  document.querySelectorAll('[data-booking-open]').forEach(button => {
    button.addEventListener('click', () => {
      if (!dialog) return;
      closeMenu();
      returnFocus = button;
      dialog.showModal();
      document.body.classList.add('is-modal-open');
      dialog.dispatchEvent(new CustomEvent('booking:open'));
      const focusTarget = dialog.querySelector('[data-scheduler]') ? document.getElementById('bookingTitle') : dialog.querySelector('input[name="name"]') || dialog.querySelector('[data-booking-close]');
      focusTarget?.focus({preventScroll: true});
    });
  });
  document.querySelectorAll('[data-booking-close]').forEach(button => button.addEventListener('click', () => dialog?.close()));
  dialog?.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  dialog?.addEventListener('close', () => {
    if (dialog.open) return;
    document.body.classList.remove('is-modal-open');
    if (success && !success.hidden) {
      form?.reset(); success.hidden = true; formWrap.hidden = false;
    }
    if (returnFocus?.getClientRects().length) returnFocus.focus({preventScroll: true});
    dialog.dispatchEvent(new CustomEvent('booking:close'));
  });
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const submit = document.getElementById('bookingSubmit');
    if (submit.disabled) return;
    const originalLabel = submit.innerHTML;
    form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
    form.querySelectorAll('[data-error-for]').forEach(error => { error.textContent = ''; });
    formError.hidden = true;
    formError.textContent = '';
    submit.disabled = true;
    submit.textContent = 'Отправляем…';
    form.setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form), signal: controller.signal,
        headers: {'Accept': 'application/json'}, credentials: 'same-origin',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        if (data.conflict) {
          dialog.dispatchEvent(new CustomEvent('booking:conflict', {detail: data}));
          return;
        }
        if (data.errors) {
          for (const [name, message] of Object.entries(data.errors)) {
            const error = form.querySelector(`[data-error-for="${name}"]`);
            const input = form.elements.namedItem(name);
            if (error) { error.textContent = message; error.id = `booking-error-${name}`; }
            if (input) { input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', `booking-error-${name}`); }
          }
          form.querySelector('[aria-invalid="true"]')?.focus();
        } else {
          formError.textContent = data.error || 'Не удалось отправить заявку. Попробуйте ещё раз.';
          formError.hidden = false;
        }
        return;
      }
      formWrap.hidden = true;
      success.hidden = false;
      dialog.dispatchEvent(new CustomEvent('booking:saved', {detail: data}));
      success.querySelector('[data-booking-close]')?.focus();
    } catch {
      formError.textContent = 'Не удалось подтвердить отправку. Проверьте соединение и попробуйте ещё раз.';
      formError.hidden = false;
    } finally {
      clearTimeout(timeout);
      submit.disabled = false;
      submit.innerHTML = originalLabel;
      form.removeAttribute('aria-busy');
    }
  });

  const catalog = document.getElementById('priceCatalog');
  if (catalog) {
    const search = document.getElementById('priceSearch');
    const groups = [...catalog.querySelectorAll('.price-group')];
    const links = [...catalog.querySelectorAll('[data-price-category]')];
    const initialCategory = location.hash.startsWith('#price-category-') ? location.hash.slice('#price-category-'.length) : '';
    let active = links.some(link => link.dataset.priceCategory === initialCategory) ? initialCategory : 'all';
    function filterPrices() {
      const query = normalize(search.value);
      let count = 0;
      groups.forEach(group => {
        let visible = 0;
        group.querySelectorAll('.price-entry').forEach(entry => {
          const match = (active === 'all' || active === group.dataset.category) && normalize(entry.dataset.search).includes(query);
          entry.hidden = !match;
          if (match) { visible++; count++; }
        });
        group.hidden = visible === 0;
      });
      document.getElementById('priceNoResults').hidden = count > 0;
      document.getElementById('priceStatus').textContent = `${count} ${plural(count, {one: 'услуга', few: 'услуги', many: 'услуг', other: 'услуг'})}`;
      links.forEach(link => {
        if (link.dataset.priceCategory === active) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
    }
    search.addEventListener('input', debounce(filterPrices));
    links.forEach(link => link.addEventListener('click', event => {
      event.preventDefault(); active = link.dataset.priceCategory; filterPrices();
      history.replaceState(null, '', location.pathname + location.search + (active === 'all' ? '' : `#price-category-${active}`));
    }));
    document.getElementById('priceReset')?.addEventListener('click', () => {
      search.value = ''; active = 'all'; filterPrices(); search.focus();
      history.replaceState(null, '', location.pathname + location.search);
    });
    filterPrices();
  }

  const patientSearch = document.getElementById('patientSearch');
  if (patientSearch) {
    const topics = [...document.querySelectorAll('.topic')];
    let previousOpen = null;
    function filterPatients() {
      const query = normalize(patientSearch.value);
      if (query && !previousOpen) previousOpen = topics.map(topic => topic.open);
      let count = 0;
      topics.forEach((topic, index) => {
        let visible = 0;
        topic.querySelectorAll('[data-search]').forEach(link => {
          const match = normalize(link.dataset.search).includes(query);
          link.hidden = !match;
          if (match) { visible++; count++; }
        });
        topic.hidden = visible === 0;
        if (query && visible) topic.open = true;
        if (!query && previousOpen) topic.open = previousOpen[index];
      });
      if (!query) previousOpen = null;
      document.getElementById('patientNoResults').hidden = count > 0;
      document.getElementById('patientStatus').textContent = `${count} ${plural(count, {one: 'материал', few: 'материала', many: 'материалов', other: 'материалов'})}`;
    }
    patientSearch.addEventListener('input', debounce(filterPatients));
    document.getElementById('patientReset')?.addEventListener('click', () => {
      patientSearch.value = ''; filterPatients(); patientSearch.focus();
    });
  }

  const toc = document.querySelector('.article-toc');
  if (toc) {
    if (window.matchMedia('(max-width: 760px)').matches) toc.open = false;
    const sections = [...document.querySelectorAll('.article-section')];
    const visible = new Set();
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => { if (entry.isIntersecting) visible.add(entry.target); else visible.delete(entry.target); });
        const current = sections.find(section => visible.has(section));
        if (!current) return;
        toc.querySelectorAll('a').forEach(link => {
          if (link.getAttribute('href') === `#${current.id}`) link.setAttribute('aria-current', 'location');
          else link.removeAttribute('aria-current');
        });
      }, {rootMargin: '-110px 0px -55% 0px', threshold: 0});
      sections.forEach(section => observer.observe(section));
    }
  }
})();
