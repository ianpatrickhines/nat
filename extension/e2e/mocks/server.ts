/**
 * Mock server for E2E tests
 *
 * This server:
 * 1. Serves mock NationBuilder pages for extension content script injection
 * 2. Provides mock API endpoints for backend communication
 */

import http from 'http';
import { URL } from 'url';

// Mock page content that simulates NationBuilder admin pages
const mockPages: Record<string, string> = {
  // Dashboard page
  '/admin': `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Dashboard - NationBuilder</title>
    </head>
    <body>
      <h1>Nation Dashboard</h1>
      <p>Welcome to your nation</p>
    </body>
    </html>
  `,

  // Person profile page
  '/admin/signups/12345': `
    <!DOCTYPE html>
    <html>
    <head>
      <title>John Doe - Profile</title>
    </head>
    <body>
      <nav class="breadcrumbs">
        <a href="/admin">Dashboard</a> &gt;
        <a href="/admin/signups">People</a> &gt;
        <span>John Doe</span>
      </nav>
      <div class="profile-header">
        <h1 class="person-name">John Doe</h1>
        <p class="location">San Francisco, CA</p>
      </div>
    </body>
    </html>
  `,

  // List page
  '/admin/lists/456': `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Volunteers - List</title>
    </head>
    <body>
      <nav class="breadcrumbs">
        <a href="/admin">Dashboard</a> &gt;
        <a href="/admin/lists">Lists</a> &gt;
        <span>Volunteers</span>
      </nav>
      <h1>Volunteers</h1>
      <p>Active volunteers list</p>
    </body>
    </html>
  `,

  // Event page
  '/admin/sites/testnation/pages/events/789': `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Town Hall Meeting - Event</title>
    </head>
    <body>
      <nav class="breadcrumbs">
        <a href="/admin">Dashboard</a> &gt;
        <a href="/admin/sites/testnation/pages/events">Events</a> &gt;
        <span>Town Hall Meeting</span>
      </nav>
      <h1>Town Hall Meeting</h1>
      <p>January 15, 2026</p>
    </body>
    </html>
  `,
};

// Mock API responses
const mockApiResponses: Record<string, unknown> = {
  // Auth state check
  'GET /api/auth/status': {
    isAuthenticated: true,
    userId: 'user-123',
    tenantId: 'tenant-456',
    nbConnected: true,
    nbNeedsReauth: false,
    subscriptionStatus: 'active',
  },

  // Streaming query response (for non-SSE tests)
  'POST /api/agent/query': {
    response: 'I found John Doe in your nation. He lives in San Francisco, CA.',
    tool_calls: [],
  },
};

// SSE streaming response for chat tests
function createSSEStream(): string[] {
  return [
    'event: text\ndata: {"content": "I found "}\n\n',
    'event: text\ndata: {"content": "John Doe"}\n\n',
    'event: text\ndata: {"content": " in your nation."}\n\n',
    'event: done\ndata: {"response": "I found John Doe in your nation.", "tool_calls": []}\n\n',
  ];
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host}`);
  const path = url.pathname;

  // Handle API requests
  if (path.startsWith('/api/')) {
    const key = `${req.method} ${path}`;

    // Handle SSE streaming endpoint
    if (path === '/api/agent/stream' && req.method === 'POST') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
      });

      const events = createSSEStream();
      let index = 0;

      const sendEvent = () => {
        if (index < events.length) {
          res.write(events[index]);
          index++;
          setTimeout(sendEvent, 50);
        } else {
          res.end();
        }
      };

      sendEvent();
      return;
    }

    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Nat-User-Id, X-Nat-Tenant-Id',
      });
      res.end();
      return;
    }

    // Return mock API response
    const response = mockApiResponses[key];
    if (response) {
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(JSON.stringify(response));
      return;
    }

    // 404 for unknown API endpoints
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
    return;
  }

  // Handle mock NB page requests
  const pageContent = mockPages[path];
  if (pageContent) {
    res.writeHead(200, {
      'Content-Type': 'text/html',
      // Simulate nationbuilder.com domain for content script matching
      'X-Test-Domain': 'nationbuilder.com',
    });
    res.end(pageContent);
    return;
  }

  // Default: serve basic page
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(`
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
      <h1>Test Page</h1>
      <p>Path: ${path}</p>
    </body>
    </html>
  `);
});

const PORT = 3456;
server.listen(PORT, () => {
  console.log(`Mock server running at http://localhost:${PORT}`);
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  server.close();
  process.exit(0);
});

export { server };
