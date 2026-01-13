/**
 * Nat Landing Page JavaScript
 * Minimal interactivity for mobile menu and smooth scrolling
 */

// Mobile menu toggle
const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
const mobileMenu = document.querySelector('.mobile-menu');

if (mobileMenuBtn && mobileMenu) {
  mobileMenuBtn.addEventListener('click', () => {
    mobileMenu.classList.toggle('active');
    // Animate hamburger to X
    mobileMenuBtn.classList.toggle('active');
  });

  // Close menu when clicking a link
  mobileMenu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      mobileMenu.classList.remove('active');
      mobileMenuBtn.classList.remove('active');
    });
  });
}

// Smooth scroll for anchor links (fallback for browsers without native support)
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    const href = (e.currentTarget as HTMLAnchorElement).getAttribute('href');
    if (href && href !== '#') {
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    }
  });
});

// Add active state to nav links based on scroll position
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('.nav-links a[href^="#"]');

const observerOptions: IntersectionObserverInit = {
  rootMargin: '-20% 0px -80% 0px'
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const id = entry.target.getAttribute('id');
      navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${id}`) {
          link.classList.add('active');
        }
      });
    }
  });
}, observerOptions);

sections.forEach(section => observer.observe(section));

// Console greeting for developers
console.log(
  '%cNat%c - NationBuilder AI Assistant',
  'color: #7c3aed; font-weight: bold; font-size: 16px;',
  'color: inherit; font-size: 14px;'
);
console.log('Interested in how Nat works? We\'re built with Claude AI.');
