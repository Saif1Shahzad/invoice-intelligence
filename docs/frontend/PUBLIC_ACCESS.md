# Public access pilot

The public entry page provides login and signup. Every registered user receives a separate PostgreSQL schema for invoices, jobs, review history, matching and exports. Opaque seven-day sessions use Secure, HttpOnly, SameSite=Lax cookies; only token hashes are stored. The original site administrator can log in with the existing username and password.

Documents → Download Excel produces a genuine `.xlsx` workbook with confirmed invoices and line items. Spreadsheet values are stored as text, so supplier text cannot execute formulas. Unconfirmed or stale records remain excluded.

Optional visitor analytics requires explicit consent. The visitor cookie retains a random identifier for 180 days and records first/last visit and visit count. Anonymous visitors are not identified. Rejecting or withdrawing clears the cookie and its visitor record. Signup does not imply outreach consent. Users may opt in to product updates and offers separately, then withdraw in their workspace.

The site administrator's **Download audience Excel** contains only opted-in email addresses and aggregate consented visitor counts. Public users cannot access this export. No outreach email is sent automatically. Email ownership is not verified; the export explicitly marks this, and the list should not be treated as verified contacts.

Pilot limits: ten upload attempts per account daily, 100 registrations daily, 200 public processing invocations daily; 3 pages / 3.5 MB per file. These limits bound abuse and API spending. Keep the workspace open during processing. Email verification, password reset, and self-service account deletion are not implemented in this pilot.
