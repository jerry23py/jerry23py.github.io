// Frontend configuration for local development and deployment.
// Edit these values before deploying the frontend to point to your live backend.

// Backend API base URL (e.g. 'https://api.example.com').
// Default is localhost for local development.
window.BACKEND_URL = window.BACKEND_URL || 'http://127.0.0.1:5000';

// Admin password for client-side auth (ONLY for simple local protection).
// For production, use server-side authentication and DO NOT store secrets in frontend files.
window.ADMIN_PASSWORD = window.ADMIN_PASSWORD || 'admin123';

// Notes:
// - When you deploy your backend, update BACKEND_URL to the deployed HTTPS URL.
// - If you want to override these values in a specific environment, set
//   `window.BACKEND_URL` or `window.ADMIN_PASSWORD` before this script runs.
