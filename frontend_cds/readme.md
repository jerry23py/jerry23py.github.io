# NYSC CDS Frontend

Frontend application for the NYSC Community Development Service (CDS) donation platform.

## Overview

This is a web-based donation management system that allows users to make donations and admins to manage and validate them. The platform features a modern interface with image galleries, donation forms, and administrative controls.

## Features

- **Donation System**: Users can submit donations with proof of payment upload
- **Gallery**: Display of community service images
- **Admin Dashboard**: Manage and validate pending donations
- **Contact Form**: Allow visitors to send messages
- **Responsive Design**: Mobile-friendly interface

## Project Structure

```
frontend_cds/
├── index.html          # Landing page
├── Donate.html         # Donation form page
├── gallery.html        # Image gallery page
├── admin.html          # Admin dashboard page
├── script.js           # Main JavaScript (site-wide functionality)
├── donate.js           # Donation form logic
├── style.css           # Styling
├── config.js           # Configuration (API endpoints, etc.)
├── API.md              # API contract documentation
├── readme.md           # This file
└── image/              # Static images directory
```

## Setup & Usage

### Running Locally

1. Open `index.html` in a web browser
2. Update `config.js` with your backend API endpoints if needed

### Key Files

- **config.js**: Update API endpoints here for different environments
- **donate.js**: Handles donation submission and file upload
- **admin.html**: Access with admin token from `/admin/login`

## API Endpoints

See [API.md](API.md) for complete API documentation.

### Main Endpoints Used

- `POST /api/contact` - Submit contact form
- `POST /donate` - Submit donation with proof file
- `POST /admin/login` - Admin authentication
- `GET /pending-donations` - Retrieve pending donations (admin only)
- `POST /admin/validate-donation` - Validate a donation (admin only)

## Authentication

Admin operations require a Bearer token:

```
Authorization: Bearer <token>
```

Or use query parameter: `?token=<token>`

## Environment Variables (Backend)

Set these on the backend server:

- `ADMIN_PASSWORD` - Strong password for admin login
- `SECRET_KEY` - Secret key for token generation

## Recent Updates

### Donation Flow (12/02/2025)

- Donations are recorded as **pending** on submission
- Users must **upload proof of payment** with donation
- Admins **manually validate** payments
- Downloads and file access are token-protected

## Development

Edit HTML files directly or use a live server for development:

```bash
# Using Python
python -m http.server 8000

# Using Node.js http-server
http-server
```

## Browser Support

Works on modern browsers:
- Chrome
- Firefox
- Safari
- Edge

## Related Documentation

- [Backend API Contract](API.md)
- [Root README](../README.md)
