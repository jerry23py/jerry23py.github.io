# API Contract — NYSC CDS Frontend ↔ Backend

## POST /api/contact
Request JSON:
{
  "name": "string",
  "email": "string",
  "phone": "string (optional)",
  "message": "string"
}

Success (200):
{
  "status": "success",
  "message": "Thank you — we received your message."
}

Error (400+):
{
  "status": "error",
  "error": "Validation error message"
}
