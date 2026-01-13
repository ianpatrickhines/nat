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

// Stripe Checkout Integration
// API endpoint - configure for production
const CHECKOUT_API_URL = import.meta.env.VITE_CHECKOUT_API_URL || 'https://api.natassistant.com/stripe/checkout';

interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

interface CheckoutError {
  error: string;
}

async function createCheckoutSession(plan: string): Promise<void> {
  const button = document.querySelector(`[data-plan="${plan}"]`) as HTMLButtonElement | null;

  if (button) {
    button.disabled = true;
    button.classList.add('loading');
    const originalText = button.textContent;
    button.textContent = 'Loading...';

    try {
      const response = await fetch(CHECKOUT_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ plan }),
      });

      const data: CheckoutResponse | CheckoutError = await response.json();

      if (!response.ok) {
        throw new Error((data as CheckoutError).error || 'Failed to create checkout session');
      }

      // Redirect to Stripe Checkout
      const checkoutData = data as CheckoutResponse;
      if (checkoutData.checkout_url) {
        window.location.href = checkoutData.checkout_url;
      } else {
        throw new Error('No checkout URL returned');
      }
    } catch (error) {
      console.error('Checkout error:', error);
      alert('Unable to start checkout. Please try again or contact support.');

      if (button) {
        button.disabled = false;
        button.classList.remove('loading');
        button.textContent = originalText;
      }
    }
  }
}

// Attach click handlers to subscribe buttons
document.querySelectorAll('[data-plan]').forEach(button => {
  button.addEventListener('click', (e) => {
    e.preventDefault();
    const plan = (e.currentTarget as HTMLElement).getAttribute('data-plan');
    if (plan) {
      createCheckoutSession(plan);
    }
  });
});

// Console greeting for developers
console.log(
  '%cNat%c - NationBuilder AI Assistant',
  'color: #7c3aed; font-weight: bold; font-size: 16px;',
  'color: inherit; font-size: 14px;'
);
console.log('Interested in how Nat works? We\'re built with Claude AI.');
