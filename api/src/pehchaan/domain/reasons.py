"""Reason catalog: every code a check can emit, what it does, and what people read.

Messages are templates, never free text, so every reason shown is true.
Add a code here before emitting it from a check; unknown codes fail the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from pehchaan.domain.models import Action, Effect


@dataclass(frozen=True)
class ReasonSpec:
    effect: Effect
    message: str
    action: Action | None = None
    strength: float = 0.0  # REJECT only: how strong the evidence is (0-1)
    flag: str | None = None  # sets a field on Flags


R = ReasonSpec

CATALOG: dict[str, ReasonSpec] = {
    # Quality gate
    "IMAGE_BLURRY": R(
        Effect.ACTION,
        "The ID photo is blurry. Hold the phone steady in good light and retake it.",
        Action.RETAKE_ID_PHOTO,
    ),
    "IMAGE_GLARE": R(
        Effect.ACTION,
        "There is glare on the ID. Tilt the card away from the light and retake it.",
        Action.RETAKE_ID_PHOTO,
    ),
    "IMAGE_TOO_SMALL": R(
        Effect.ACTION, "The ID photo is too small to read. Move closer and retake it.", Action.RETAKE_ID_PHOTO
    ),
    "DOCUMENT_NOT_FOUND": R(
        Effect.ACTION,
        "We couldn't find an ID card in the photo. Place the whole card inside the frame.",
        Action.RETAKE_ID_PHOTO,
    ),
    "SCREEN_RECAPTURE": R(
        Effect.ACTION,
        "This looks like a photo of a screen. Photograph the physical card or upload your e-Aadhaar PDF.",
        Action.USE_ORIGINAL_DOCUMENT,
    ),
    "PDF_UNREADABLE": R(
        Effect.ACTION,
        "We couldn't open this PDF. Upload a photo of your card, or the e-Aadhaar PDF with its password removed.",
        Action.RETAKE_ID_PHOTO,
    ),
    "IMAGE_UNREADABLE": R(
        Effect.ACTION, "We couldn't read this file as an image. Upload a JPEG or PNG photo.", Action.RETAKE_ID_PHOTO
    ),
    # Extraction
    "FIELDS_UNREADABLE": R(
        Effect.ACTION,
        "We couldn't read the {fields} on your ID. Retake the photo with the text in focus.",
        Action.RETAKE_ID_PHOTO,
    ),
    "DOC_TYPE_UNKNOWN": R(Effect.REVIEW, "We couldn't tell which kind of ID this is."),
    "LOW_OCR_CONFIDENCE": R(Effect.PENALTY, "Some fields were hard to read: {fields}."),
    # Document rules
    "ID_NUMBER_VALID": R(Effect.INFO, "The {doc_type} number has a valid format."),
    "ID_NUMBER_MASKED": R(Effect.INFO, "The Aadhaar number is masked, so only the last 4 digits were checked."),
    "ID_NUMBER_INVALID": R(Effect.REVIEW, "The {doc_type} number doesn't pass its format check."),
    "PAN_NOT_INDIVIDUAL": R(Effect.REVIEW, "This PAN belongs to an organisation, not a person."),
    "PAN_SURNAME_INITIAL_MISMATCH": R(Effect.PENALTY, "The PAN's name letter doesn't match any initial in the name."),
    "DOB_IMPLAUSIBLE": R(Effect.REVIEW, "The date of birth on the ID isn't plausible."),
    # Aadhaar Secure QR
    "AADHAAR_QR_VERIFIED": R(Effect.INFO, "The Aadhaar QR code carries a valid UIDAI signature and matches the card."),
    "AADHAAR_QR_NOT_FOUND": R(Effect.INFO, "No Aadhaar QR code could be read from this photo."),
    "AADHAAR_QR_REQUIRED": R(
        Effect.ACTION,
        "This event checks the QR code on your Aadhaar. Photograph the card so the QR code is fully visible and sharp, or upload your e-Aadhaar PDF.",
        Action.RETAKE_ID_PHOTO,
    ),
    "AADHAAR_QR_MISSING_AFTER_RETAKE": R(
        Effect.REVIEW, "The Aadhaar QR code still couldn't be read after a retake, so a person will check the card."
    ),
    "AADHAAR_QR_SIGNATURE_INVALID": R(Effect.REVIEW, "The Aadhaar QR code's signature could not be validated."),
    "AADHAAR_PRINT_CONTRADICTS_QR": R(
        Effect.REJECT, "The {field} printed on the card differs from the UIDAI-signed QR code.", strength=0.95
    ),
    "AADHAAR_PHOTO_MISMATCH_QR": R(
        Effect.REVIEW, "The photo on the card doesn't match the photo in the signed QR code."
    ),
    "AADHAAR_PRINT_QR_MISMATCH": R(
        Effect.REVIEW, "The {field} read from the card differs from the signed QR code (it may be a misread)."
    ),
    "AADHAAR_QR_LEGACY_UNSIGNED": R(
        Effect.INFO, "This is an older, unsigned Aadhaar QR code, so it can't prove the card."
    ),
    "AADHAAR_QR_CERT_MISSING": R(
        Effect.INFO, "No UIDAI certificate is configured, so the QR signature wasn't checked."
    ),
    "AADHAAR_QR_UNREADABLE": R(Effect.INFO, "A QR code was found but it isn't a readable Aadhaar Secure QR."),
    # Edit and recapture signals
    "TAMPER_SUSPECTED_FIELD": R(Effect.REVIEW, "Possible edit in the {field} area."),
    "EDITING_SOFTWARE_METADATA": R(Effect.REVIEW, "The image was saved by editing software ({software})."),
    "TEXT_GEOMETRY_ANOMALY": R(Effect.REVIEW, "The {field} line is misaligned with the rest of the card."),
    # Duplicates
    "DUPLICATE_ID_OTHER_IDENTITY": R(
        Effect.REVIEW,
        "This ID is already used by another registration under a different name.",
        flag="duplicate_suspected",
    ),
    "DUPLICATE_IMAGE": R(
        Effect.REVIEW, "This exact ID image was used in another registration.", flag="duplicate_suspected"
    ),
    "DUPLICATE_FACE_OTHER_IDENTITY": R(
        Effect.REVIEW,
        "The face on this ID appears in another registration with a different ID.",
        flag="duplicate_suspected",
    ),
    "DUPLICATE_LATER_REGISTRATION": R(
        Effect.REVIEW,
        "A later registration used the same ID, photo or face under a different name.",
        flag="duplicate_suspected",
    ),
    "SAME_PERSON_KNOWN": R(Effect.INFO, "This person has used this ID before under the same name."),
    "DEVICE_SHARED_BY_MANY": R(
        Effect.REVIEW,
        "This device was used to register {count} different identities.",
        flag="duplicate_suspected",
    ),
    "DUPLICATE_INDEX_UNAVAILABLE": R(Effect.REVIEW, "The duplicate check couldn't run, so a person will look at this."),
    # Identity match
    "NAME_MATCH": R(Effect.INFO, "The name on the ID matches the registration."),
    "NAME_PARTIAL_MATCH": R(Effect.REVIEW, "The name on the ID only partly matches the registration ({detail})."),
    "NAME_MISMATCH": R(Effect.REVIEW, "The name on the ID doesn't match the registration."),
    "DOB_MISMATCH_FORM": R(Effect.REVIEW, "The date of birth on the ID differs from the registration form."),
    "EMAIL_DOMAIN_MATCHES_INSTITUTION": R(Effect.INFO, "The college email domain matches the institution."),
    "VERIFIED_COLLEGE_EMAIL": R(
        Effect.INFO, "The participant has confirmed a college email address at this institution."
    ),
    "INSTITUTION_NOT_RECOGNISED": R(Effect.PENALTY, "The institution wasn't found in the AISHE registry."),
    # Selfie
    "SELFIE_MATCH": R(Effect.INFO, "The selfie matches the photo on the ID."),
    "SELFIE_MISMATCH": R(Effect.REVIEW, "The selfie doesn't clearly match the photo on the ID."),
    "SELFIE_SPOOF_SUSPECTED": R(
        Effect.ACTION, "The selfie looks like a photo of a photo or screen. Take a live selfie.", Action.RETAKE_SELFIE
    ),
    "SELFIE_REQUIRED": R(Effect.ACTION, "This event needs a selfie to confirm it's you.", Action.RETAKE_SELFIE),
    "SELFIE_NO_FACE": R(
        Effect.ACTION, "We couldn't find a face in the selfie. Face the camera in good light.", Action.RETAKE_SELFIE
    ),
    "SELFIE_NOT_LIVE_CAPTURE": R(
        Effect.PENALTY, "The selfie was uploaded as a file rather than taken with the camera."
    ),
    "SELFIE_NO_REFERENCE": R(Effect.INFO, "There was no clear photo on the ID to compare the selfie with."),
    # Eligibility
    "AGE_ELIGIBLE": R(Effect.INFO, "Age {age} on the event date is within the event's limits."),
    "AGE_BELOW_MIN_CONFIRMED": R(
        Effect.REJECT, "Age {age} on the event date is below this event's minimum of {min_age}.", strength=0.9
    ),
    "AGE_ABOVE_MAX_CONFIRMED": R(
        Effect.REJECT, "Age {age} on the event date is above this event's maximum of {max_age}.", strength=0.9
    ),
    "AGE_OUT_OF_RANGE_UNCONFIRMED": R(
        Effect.REVIEW, "The date of birth suggests age {age}, outside the event's limits, but it couldn't be confirmed."
    ),
    "AGE_UNKNOWN": R(Effect.REVIEW, "The date of birth couldn't be determined."),
    "AGE_BOUNDARY_UNCERTAIN": R(
        Effect.REVIEW, "Only the year of birth is known and the age limit falls within that year."
    ),
    "MINOR_GUARDIAN_CONSENT": R(
        Effect.INFO,
        "The participant is under {under} on the event date; a guardian must consent.",
        flag="guardian_consent_required",
    ),
    "DOC_TYPE_NOT_ACCEPTED": R(
        Effect.ACTION,
        "This event doesn't accept {doc_type}. Upload one of: {accepted}.",
        Action.UPLOAD_ACCEPTED_DOCUMENT,
    ),
    "STUDENT_PROOF_REQUIRED": R(
        Effect.ACTION, "This event is for students. Upload your current college ID.", Action.UPLOAD_COLLEGE_ID
    ),
    "COLLEGE_ID_EXPIRED": R(
        Effect.ACTION, "Your college ID expired on {valid_until}. Upload a current one.", Action.UPLOAD_COLLEGE_ID
    ),
    "COLLEGE_ID_VALIDITY_UNKNOWN": R(Effect.PENALTY, "The college ID's validity date couldn't be read."),
    # Engine
    "CHECK_ERROR": R(Effect.REVIEW, "An automatic check ({check}) couldn't finish, so a person will look at this."),
    "LEVEL_BELOW_EVENT_MINIMUM": R(Effect.REVIEW, "There isn't enough evidence to verify automatically."),
}


def render(code: str, params: dict[str, str | int | float]) -> str:
    spec = CATALOG[code]
    try:
        return spec.message.format(**params)
    except (KeyError, IndexError):
        return spec.message
