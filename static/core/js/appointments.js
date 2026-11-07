(() => {
  'use strict';
  const scheduler = document.querySelector('[data-scheduler]');
  if (!scheduler) return;
  const el = id => document.getElementById(id);
  const dialog = el('bookingDialog');
  const grid = el('scheduleGrid');
  const tabs = el('scheduleDayTabs');
  const status = el('scheduleStatus');
  const previous = dialog.querySelector('[data-week-previous]');
  const next = dialog.querySelector('[data-week-next]');
  let calendar, selected = null, activeDay = '', loading, poll;
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }
  function selectDay(date) {
    activeDay = date;
    grid.querySelectorAll('[data-date]').forEach(day => day.classList.toggle('is-active', day.dataset.date === date));
    tabs.querySelectorAll('button').forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.date === date)));
  }
  function selectSlot(slot) {
    selected = slot;
    dialog.classList.toggle('has-selection', Boolean(slot));
    grid.querySelectorAll('[data-slot]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.slot) === slot?.id)));
    el('scheduleContinue').disabled = !slot;
    el('scheduleSelectedLabel').textContent = slot?.label || 'Выберите свободное окно';
    el('scheduleSelectedService').textContent = slot ? `${slot.service} · ${slot.duration} минут` : 'Окно будет занято после отправки формы';
  }
  function render(data) {
    calendar = data;
    el('scheduleWeekLabel').textContent = data.week_label;
    previous.disabled = !data.previous;
    next.disabled = !data.next;
    el('scheduleDemoNotice').hidden = !data.has_demo;
    grid.replaceChildren(); tabs.replaceChildren();
    let free = 0;
    data.days.forEach(day => {
      const tab = node('button'); tab.type = 'button'; tab.dataset.date = day.date;
      tab.append(node('span', day.label), node('strong', String(day.number)));
      tab.setAttribute('aria-label', `${day.label}, ${day.date}`);
      tab.addEventListener('click', () => selectDay(day.date));
      tabs.append(tab);
      const section = node('section', undefined, 'schedule-day'); section.dataset.date = day.date;
      const heading = node('h4', undefined, 'schedule-day-heading');
      heading.append(node('span', day.label), node('strong', String(day.number))); section.append(heading);
      const list = node('div', undefined, 'schedule-day-slots');
      day.slots.forEach(slot => {
        const button = node('button', undefined, 'schedule-slot'); button.type = 'button';
        button.dataset.slot = slot.id;
        button.disabled = slot.status !== 'free';
        const label = slot.status === 'free' ? 'Свободно' : slot.status === 'busy' ? 'Занято' : 'Закрыто';
        button.append(node('span', slot.time), node('small', label));
        button.setAttribute('aria-label', `${slot.label}, ${slot.service}, ${label.toLowerCase()}`);
        button.setAttribute('aria-pressed', 'false');
        button.addEventListener('click', () => { selectSlot(slot); selectDay(day.date); });
        list.append(button);
        if (slot.status === 'free') free++;
      });
      if (!day.slots.length) list.append(node('p', 'Нет приёма', 'schedule-day-empty'));
      section.append(list); grid.append(section);
    });
    if (!data.days.some(day => day.date === activeDay)) {
      activeDay = (data.days.find(day => day.slots.some(slot => slot.status === 'free')) || data.days[0]).date;
    }
    selectDay(activeDay);
    const refreshed = data.days.flatMap(day => day.slots).find(slot => slot.id === selected?.id && slot.status === 'free');
    selectSlot(refreshed || null);
    status.textContent = free ? 'Выберите удобное время консультации.' : 'На этой неделе свободных окон нет. Посмотрите следующую неделю.';
  }
  async function load(week, message = '') {
    loading?.abort();
    const controller = new AbortController(); loading = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    grid.setAttribute('aria-busy', 'true');
    status.textContent = 'Обновляем расписание…';
    el('scheduleRetry').hidden = true;
    el('scheduleContinue').disabled = true;
    grid.querySelectorAll('button').forEach(button => { button.disabled = true; });
    try {
      const url = new URL(scheduler.dataset.slotsUrl, location.origin);
      if (week) url.searchParams.set('week', week);
      const response = await fetch(url, {signal: controller.signal, credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Не удалось загрузить расписание.');
      render(data);
      if (message) status.textContent = message;
    } catch (error) {
      if (loading !== controller) return;
      status.textContent = error.name === 'AbortError' ? 'Расписание не ответило вовремя. Попробуйте обновить.' : error.message;
      el('scheduleRetry').hidden = false;
      // Keep stale buttons unclickable until availability can be checked again.
      grid.querySelectorAll('button').forEach(button => { button.disabled = true; });
    } finally {
      clearTimeout(timeout);
      if (loading === controller) { grid.removeAttribute('aria-busy'); loading = null; }
    }
  }
  function chooseView() {
    dialog.classList.remove('is-details');
    el('scheduleChoice').hidden = false;
    el('scheduleDetails').hidden = true;
    el('scheduleStepOne').setAttribute('aria-current', 'step');
    el('scheduleStepTwo').removeAttribute('aria-current');
  }
  previous.addEventListener('click', () => { selectSlot(null); activeDay = ''; load(calendar?.previous); });
  next.addEventListener('click', () => { selectSlot(null); activeDay = ''; load(calendar?.next); });
  el('scheduleRetry').addEventListener('click', () => load(calendar?.week_start));
  el('scheduleContinue').addEventListener('click', () => {
    if (!selected) return;
    el('bookingSlot').value = selected.id;
    el('scheduleDetailsService').textContent = selected.service;
    el('scheduleDetailsTime').textContent = selected.label;
    el('scheduleDetailsDuration').textContent = `${selected.duration} минут · время московское`;
    el('scheduleDetailsDemo').hidden = !selected.demo;
    el('scheduleDemoConsent').hidden = !selected.demo;
    el('scheduleChoice').hidden = true;
    el('scheduleDetails').hidden = false;
    dialog.classList.add('is-details');
    el('scheduleStepTwo').setAttribute('aria-current', 'step');
    el('scheduleStepOne').removeAttribute('aria-current');
    el('bookingName').focus({preventScroll: true});
    dialog.scrollTop = 0;
  });
  el('scheduleBack').addEventListener('click', () => { chooseView(); load(calendar?.week_start); dialog.scrollTop = 0; });
  dialog.addEventListener('booking:open', () => {
    chooseView(); selectSlot(null); load(calendar?.week_start);
    clearInterval(poll);
    poll = setInterval(() => {
      if (!document.hidden && !el('scheduleChoice').hidden && !loading) load(calendar?.week_start);
    }, 20000);
  });
  dialog.addEventListener('booking:close', () => { clearInterval(poll); loading?.abort(); chooseView(); });
  dialog.addEventListener('booking:conflict', event => {
    selectSlot(null); chooseView();
    load(calendar?.week_start, event.detail.error);
    dialog.scrollTop = 0;
  });
  dialog.addEventListener('booking:saved', event => {
    clearInterval(poll);
    el('scheduleSuccessText').textContent = `Бронь №${event.detail.booking_id} · ${selected?.label || ''}. ${scheduler.dataset.successText}`;
    el('scheduleSuccessDemo').hidden = !event.detail.demo;
    selectSlot(null);
    dialog.scrollTop = 0;
  });
  if (location.hash === '#appointment') document.querySelector('[data-booking-open]')?.click();
})();
