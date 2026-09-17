"""Heavy, shared resources loaded once at startup."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pehchaan.aadhaar.secure_qr import CertificateStore
from pehchaan.config import Settings
from pehchaan.institutions import InstitutionRegistry
from pehchaan.ocr.rapid import RapidOcrEngine
from pehchaan.ocr.textract import TextractClient
from pehchaan.security import Crypto
from pehchaan.store.sqlite import Store
from pehchaan.vision.faces import FaceEngine
from pehchaan.vision.qr import QrReader

logger = logging.getLogger(__name__)


@dataclass
class Engines:
    settings: Settings
    crypto: Crypto
    store: Store
    faces: FaceEngine | None
    qr: QrReader
    certificates: CertificateStore
    textract: TextractClient | None
    rapid: RapidOcrEngine | None
    institutions: InstitutionRegistry

    @classmethod
    def load(cls, settings: Settings) -> Engines:
        crypto = Crypto.from_settings(settings)
        store = Store(settings.data_dir / "pehchaan.db", crypto)

        textract = None
        if settings.ocr_provider in {"auto", "textract"} and settings.textract_enabled:
            textract = TextractClient(settings.aws_region)
        rapid = RapidOcrEngine() if settings.ocr_provider in {"auto", "rapidocr"} else None

        certificates = CertificateStore.load(settings.uidai_cert_path)
        if not certificates.available:
            logger.warning(
                "no UIDAI certificates at %s; Aadhaar QR signatures won't be verified", settings.uidai_cert_path
            )

        return cls(
            settings=settings,
            crypto=crypto,
            store=store,
            faces=FaceEngine.load(settings.models_dir),
            qr=QrReader(settings.models_dir),
            certificates=certificates,
            textract=textract,
            rapid=rapid,
            institutions=InstitutionRegistry.load(settings.institutions_csv),
        )

    def status(self) -> dict[str, object]:
        return {
            "ocr": "textract" if self.textract else "rapidocr" if self.rapid else None,
            "faces": self.faces is not None,
            "uidai_certificates": [name for name, _ in self.certificates.keys],
            "institution_registry": self.institutions.available,
        }
