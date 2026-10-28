# Portfolio demo walkthrough

1. Start the combined launcher. Show the active worker indicator and evaluation page, explaining that the model is currently local rules + Tesseract.
2. Open clean invoice 0001. Highlight Total's source location. Show its matching PO and image duplicate candidate.
3. Compare both sources and choose the PDF as canonical with a reviewer/reason. Show that the image record cannot be confirmed independently.
4. Open invoice 0002. Explain the printed total differs from the arithmetic result; do not describe a correctly extracted wrong printed amount as an OCR error.
5. Open invoice 0005. Its synthetic PO has deliberate quantity and unit-price differences. Show that an exception requires explicit acknowledgment and a recorded reason.
6. Start an automated-demo timer for a scripted demonstration, or a human-pilot timer for real human work. Pause/resume, correct/check, and decide. Show the saved timing group honestly.
7. Reload history, then export a current confirmed record. Repeated source upload reuses the stored record.
8. Show the rotated scan, two-page fixture, blank image and reserved layout. Explain their review reasons; malformed input is rejected. The reserved layout is a single smoke test, not unseen-template accuracy evidence.
9. Present the frozen test figures: 42 business invoices / 84 file variants, shared templates, 1093/1098 positive header values, 1445/1468 item cells, duplicate 41 TP / 1 FN / 0 FP / 3444 TN. Show the errors/limits rather than claiming perfection.
10. Close with the explicit supported scope: local single-user, every invoice human-confirmed, no payment or accounting-system writes. Human labor savings remain unmeasured until the pilot.
