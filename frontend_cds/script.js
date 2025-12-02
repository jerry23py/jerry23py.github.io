// script.js

// Mobile hamburger toggle
const hamburger = document.querySelector('.hamburger');
const navList = document.querySelector('.nav-list');

if (hamburger) {
  hamburger.addEventListener('click', () => {
    const expanded = hamburger.getAttribute('aria-expanded') === 'true';
    hamburger.setAttribute('aria-expanded', String(!expanded));
    navList.classList.toggle('open');
  });
}

// Contact form handling (mock)
const form = document.getElementById('contactForm');
const statusDiv = document.getElementById('formStatus');

if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    // simple client-side validation
    const name = form.name.value.trim();
    const email = form.email.value.trim();
    const message = form.message.value.trim();
    if (!name || !email || !message) {
      statusDiv.textContent = 'Please fill required fields.';
      statusDiv.style.color = 'crimson';
      return;
    }

    // show loading state
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending…';
    statusDiv.textContent = 'Sending message...';
    statusDiv.style.color = '';

    // MOCK API call (replace with real endpoint later)
    try {
      await new Promise(r => setTimeout(r, 1200)); // simulate network
      // pretend success response
      statusDiv.textContent = 'Thank you — we received your message.';
      statusDiv.style.color = 'green';
      form.reset();
    } catch (err) {
      statusDiv.textContent = 'Error sending message. Try again.';
      statusDiv.style.color = 'crimson';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}

  // Hero slider — rotates slides, has prev/next controls, pauses on hover
  (function setupHeroSlider(){
    const slider = document.querySelector('.hero-slider');
    if (!slider) return;
    const slides = Array.from(slider.querySelectorAll('.slide'));
    if (slides.length === 0) return;
    let current = 0;
    let intervalId = null;

    function show(index){
      slides.forEach((s,i)=> s.classList.toggle('active', i === index));
      current = index;
    }

    function next(){
      show((current + 1) % slides.length);
    }

    function prev(){
      show((current - 1 + slides.length) % slides.length);
    }

    // initial
    show(0);

    // auto-rotate
    function start(){ intervalId = setInterval(next, 4000); }
    function stop(){ if (intervalId) { clearInterval(intervalId); intervalId = null; } }
    start();

    // controls
    const nextBtn = document.querySelector('.slider-next');
    const prevBtn = document.querySelector('.slider-prev');
    if (nextBtn) nextBtn.addEventListener('click', () => { stop(); next(); start(); });
    if (prevBtn) prevBtn.addEventListener('click', () => { stop(); prev(); start(); });

    // pause on hover
    slider.addEventListener('mouseenter', stop);
    slider.addEventListener('mouseleave', start);
  })();

  // Compact gallery slider
  (function setupGallery(){
    const wrap = document.querySelector('.gallery-wrap');
    if (!wrap) return;
    const slider = wrap.querySelector('.gallery-slider');
    const slides = Array.from(slider.querySelectorAll('.g-slide'));
    if (!slides.length) return;
    let current = 0;
    let id = null;

    function show(i){
      slides.forEach((s,idx)=> s.classList.toggle('active', idx===i));
      current = i;
    }
    function next(){ show((current+1) % slides.length); }
    function prev(){ show((current-1+slides.length) % slides.length); }

    show(0);
    function start(){ id = setInterval(next, 3500); }
    function stop(){ if (id) { clearInterval(id); id = null; } }
    start();

    const nextBtn = wrap.querySelector('.gallery-next');
    const prevBtn = wrap.querySelector('.gallery-prev');
    if (nextBtn) nextBtn.addEventListener('click', ()=>{ stop(); next(); start(); });
    if (prevBtn) prevBtn.addEventListener('click', ()=>{ stop(); prev(); start(); });

    slider.addEventListener('mouseenter', stop);
    slider.addEventListener('mouseleave', start);
  })();
