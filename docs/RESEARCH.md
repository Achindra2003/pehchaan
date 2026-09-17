# Research notes

Compiled 17 Sep 2026 for PS-003 (Hackingly platform track, AI Build Challenge, Bengaluru, 18 Sep 2026).
Everything here is sourced. Items we could not confirm are marked **unverified**.

## 1. Who is judging and what they will probe

| Judge's company | What they are likely to push on | Where Pehchaan answers it |
|---|---|---|
| **Hackingly** (problem owner; co-founder & CEO Avni Srivastava) | Integration effort, genuine students never blocked, manual review hours saved, cost per verification, whether it becomes a platform advantage | One API call after the existing Textract step, shadow-mode rollout, auto-verify rate, cost model, reusable verified status across events |
| **RevRag.ai** (agentic AI for enterprises/BFSI; CEO Ashutosh Prakash Singh) | Whether the AI is real or decoration, KYC-grade rigour, auditability | Grounded extraction, reviewer copilot, reason codes, hash-chained audit log |
| **Qualcomm** | Efficiency, on-device inference, model size and latency | Capture checks run in the browser; every model is a small ONNX file (YuNet, SFace, MiniFASNet) |
| **PeerPatch** | No public information found (**unverified**); treat as a general product/startup lens | — |
| **Masters' Union / MU Ventures** (organiser) | Business viability, scale, execution quality | Unit economics, multi-tenant design, working prototype with measured numbers |

## 2. The finding that shapes the whole design: pixels can no longer be trusted

- **AIForge-Doc (Feb 2026)** forged fields in real documents with AI inpainting. Existing detectors collapsed out of distribution: TruFor AUC 0.751, DocTamper AUC 0.563, and a zero-shot **GPT-4o judge AUC 0.509, essentially chance**.
- **ID-document forgery survey (Jul 2026)**: zero-shot multimodal models reach **EER above 45% on ID cards**; public forensic models show **APCER above 25%** on unseen synthetic IDs. Recapture detection (print/screen artefacts) still works against physical attacks but not against digitally injected forgeries.
- The same survey cites a **2025 Bengaluru demonstration where a generative model produced realistic Aadhaar and PAN replicas**.

**Implication.** A "vision model looks at the card" approach cannot be the backbone. Pehchaan orders its trust:
1. **What is cryptographically signed** (Aadhaar Secure QR; in production, DigiLocker / Aadhaar App verifiable credentials).
2. **What must agree across sources** (form, OCR, QR, face, college email domain, institution registry).
3. **What the platform has already seen** (the same ID, image or face under a different identity across all Hackingly events).
4. **What the pixels suggest** (recapture, local edit traces, metadata, VLM second opinion): soft signals that can only send a case to review, never reject.

## 3. Regulatory and platform ground truth

**Aadhaar Secure QR**
- Printed on every Aadhaar letter, card and e-Aadhaar. It holds a reference ID (last 4 digits of Aadhaar plus a timestamp), name, DOB, gender, address, a JPEG 2000 photo and email/mobile indicators, **signed by UIDAI with a 2048-bit RSA / SHA-256 signature**. The payload is a base-10 big integer, gzip-compressed, fields separated by byte `255`, **signature = last 256 bytes**.
- It can be verified offline with UIDAI's public certificate. The URL referenced by UIDAI's FAQ (`uidai_offline_publickey_26022019.cer`) returned 404 from our fetch (possibly geo-restricted). **Download the current certificate from the UIDAI developer section from an Indian network and test against a real e-Aadhaar before relying on it.**
- In latest QR versions UIDAI does not expose the full Aadhaar number.

**Offline verification rules (OVSE)**
- Governed by the *Aadhaar (Authentication and Offline Verification) Amendment Regulations, 2025*. Event organisers and hotels are named as offline-verification-seeking entities that will need registration.
- Secure QR verification is **display-only: no storage** of the QR data. Pehchaan stores only the outcome and the last 4 digits.
- UIDAI plans to stop private entities storing Aadhaar photocopies; the **new Aadhaar App (launched Jan 2026)** shares signed verifiable credentials with **selective disclosure (for example age status only)** and offline face verification. This is the production path for Aadhaar holders.

**DPDP**
- DPDP Rules 2025 were notified in Nov 2025 with a phased rollout. Consent, security safeguards, breach reporting, retention and **verifiable parental consent for under-18s become enforceable on 13 May 2027**. Existing identity/age records, tokens or DigiLocker are recognised ways to verify the parent.
- Pitch line: *Pehchaan makes Hackingly compliant before the deadline, not after.*

**DigiLocker Requester API**
- OAuth consent, then pull signed documents (Aadhaar, PAN). It requires MeitY onboarding through API Setu, so it is **not feasible for the hackathon**; it is on the production roadmap and mocked in the demo.

**Amazon Textract**
- Text languages: English, Spanish, Italian, Portuguese, French, German. **No Hindi or other Indian scripts.** Queries and ID analysis are English only.
- `AnalyzeID` only supports passports and US driving licences, so for Indian IDs we use `DetectDocumentText` plus `AnalyzeDocument` Queries.
- List prices (US West, first 1M pages): DetectDocumentText **$1.50 / 1k pages**, Queries **$15 / 1k**, AnalyzeID $25 / 1k. Mumbai pricing not confirmed (**unverified**).

## 4. Build vs reuse

| Need | Adopt | License | Notes |
|---|---|---|---|
| Secure QR decode | [pyaadhaar](https://github.com/tanmoysrt/pyaadhaar) logic, vendored | MIT | Handles V2/V3/V5 layouts, exposes `signedData()` / `signature()`. **Does not verify the RSA signature**: we add that with `cryptography`. Vendored to avoid its `opencv-python` dependency clashing with `opencv-contrib`. |
| QR detection on phone photos | OpenCV `wechat_qrcode` (opencv-contrib, pinned `<5`) | Apache-2.0 | CNN-assisted detector, better on dense and small codes than zbar |
| ID number validation | [python-stdnum](https://pypi.org/project/python-stdnum/) `in_.aadhaar` (Verhoeff), `in_.pan`, `in_.epic`, `in_.vid` | LGPL | Used as a library dependency only |
| Indian name matching | [indic-namematch](https://github.com/kiranshivaraju/indic-namematch) 0.1.0 | MIT | Initials, surname-first, transliteration, honorifics, patronymics, OCR noise; rarity-weighted; 253 tests. Brand new (0 stars), so pin it and keep our own regression cases |
| OCR (existing) | Amazon Textract + [amazon-textract-textractor](https://pypi.org/project/amazon-textract-textractor/) | Apache-2.0 | Reuse Hackingly's Textract JSON when supplied; only call Queries when fields are missing |
| OCR fallback for Devanagari | PaddleOCR PP-OCRv5 `devanagari_PP-OCRv5_mobile_rec` | Apache-2.0 | Optional; heavy, only if time allows |
| Face detection | OpenCV Zoo YuNet `2023mar` | MIT | Faces roughly 10–300 px, ideal for ID photos |
| Face matching | OpenCV Zoo SFace `2021dec` | Apache-2.0 | MobileFaceNet, 99.40% LFW |
| Selfie anti-spoofing | MiniFASNet-V2 ONNX (from minivision Silent-Face-Anti-Spoofing) | Apache-2.0 | ~600 KB; live / print / replay classes |
| On-device capture guidance | MediaPipe Face Detection (Tasks Vision, WASM) | Apache-2.0 | Also published on **Qualcomm AI Hub**, a useful talking point |
| Duplicate images | [pdqhash](https://github.com/faustomorales/pdqhash-python) + imagehash | MIT bindings (PDQ source licensed separately) / BSD | Near-duplicate detection robust to re-compression and crops |
| Institution registry | AISHE college list (data.gov.in) | Open Government Data | Validates institutions for student-only events |
| Review UX reference | [Ballerine](https://github.com/ballerine-io/ballerine) | open source | Reference for case-management UX only; too heavy to adopt |

**Deliberately avoided**
- **TruFor**: license limits use to informational, non-profit purposes.
- **DocTamper dataset**: non-commercial, application required.
- **InsightFace pretrained models**: non-commercial research only (**verify before quoting**).
- **AadhaarQRCodeReader** (GPL-3.0): reference only; no code copied.

## 5. Competitive landscape

- **IDfy, HyperVerge, Signzy** are BFSI-grade KYC suites with quote-only pricing. **Setu** DigiLocker verification is reported at about ₹5 per verification (unofficial).
- None of them are **event-eligibility aware** (age on event date, student-only, accepted documents), and none can use **Hackingly's own cross-event participant graph**, the strongest duplicate signal available.
- Pehchaan's position: purpose-built eligibility verification that costs a few paise of OCR where Hackingly already pays for Textract, and gets better with every event.

## 6. Open items

- [ ] Ask Hackingly for the **anonymised sample IDs** (the problem statement says they are available on request). Do this today.
- [ ] Download the **UIDAI offline verification certificate** from an Indian network; test on a team member's e-Aadhaar.
- [ ] AWS credentials with Textract in `ap-south-1`; confirm Mumbai pricing.
- [ ] Find out what PeerPatch does.

## Sources

- [AIForge-Doc benchmark (arXiv 2602.20569)](https://arxiv.org/html/2602.20569v1)
- [From Forgeries to Foundation Models: survey of ID document attack and detection (arXiv 2607.01442)](https://arxiv.org/html/2607.01442v1)
- [DocTamper (CVPR 2023)](https://github.com/qcf-568/DocTamper)
- [TruFor](https://github.com/grip-unina/TruFor)
- [pyaadhaar](https://github.com/tanmoysrt/pyaadhaar) · [PyPI](https://pypi.org/project/pyaadhaar/)
- [AadhaarQRCodeReader write-up](https://dev.to/ptprashanttripathi/i-built-an-aadhaar-qr-reader-that-works-100-offline-no-server-no-data-leak-5dcg)
- [UIDAI: what the Secure QR contains](https://uidai.gov.in/en/306-english-uk/faqs/2023-09-09-07-12-17/2023-09-09-07-19-00/aadhaar-online-services/secure-qr-code-reader-beta/10781-what-is-uidai-secure-qr-code-how-qr-code-enhance-the-security-of-e-aadhaar.html)
- [UIDAI: public certificate for signature validation](https://uidai.gov.in/en/307-faqs/aadhaar-online-services/aadhaar-paperless-offline-e-kyc/12001-where-can-i-find-the-public-certificate-for-digital-signature-validation.html)
- [UIDAI: offline verification and OVSEs](https://uidai.gov.in/en/contact-support/have-any-question/1039-english-uk/faqs/authentication/offline-verification-and-role-of-ovses-under-authentication-eco-system.html)
- [Gridlines: Aadhaar offline verification and OVSE guide](https://gridlines.io/blogs/what-is-aadhaar-offline-verification/)
- [New Aadhaar App explained](https://www.convergence-now.com/explainers/new-aadhaar-app-explained-features-privacy-uses-and-how-it-works/)
- [Deccan Herald: UIDAI plans to ban storing Aadhaar photocopies](https://www.deccanherald.com/india/uidai-plans-to-ban-private-entities-form-storing-aadhaar-photocopies-here-is-the-alternative-3826236)
- [Xident: DPDP age verification and parental consent before May 2027](https://xident.io/blog/india-dpdp-age-verification-verifiable-parental-consent-childrens-data-2026/)
- [Seclore: DPDP Rules 2025 compliance guide](https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/)
- [API Setu: DigiLocker](https://apisetu.gov.in/digilocker) · [Setu DigiLocker docs](https://docs.setu.co/data/digilocker/quickstart)
- [Amazon Textract pricing](https://aws.amazon.com/textract/pricing/) · [Textract FAQs](https://aws.amazon.com/textract/faqs) · [AnalyzeID API](https://docs.aws.amazon.com/ko_kr/textract/latest/dg/API_AnalyzeID.html)
- [python-stdnum Aadhaar module](https://arthurdejong.org/python-stdnum/doc/1.20/stdnum.in_.aadhaar)
- [indic-namematch](https://github.com/kiranshivaraju/indic-namematch)
- [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) · [SFace](https://huggingface.co/opencv/face_recognition_sface)
- [Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing) · [MiniFASNet-V2 ONNX](https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx)
- [MediaPipe Face Detection on Qualcomm AI Hub](https://aihub.qualcomm.com/compute/models/mediapipe_face)
- [PaddleOCR PP-OCRv5 multilingual](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md)
- [pdqhash-python](https://github.com/faustomorales/pdqhash-python)
- [AISHE list of colleges (data.gov.in)](https://www.data.gov.in/catalog/list-colleges-aishe-survey)
- [Recapture detection: CMA (CVPR 2024)](https://github.com/chenlewis/Chromaticity-Map-Adapter-for-DPAD)
- [Ballerine](https://github.com/ballerine-io/ballerine)
- [KYC API providers in India (Gridlines)](https://gridlines.io/blogs/top-11-kyc-api-providers-in-india/) · [Aadhaar verification API comparison (Hypersign)](https://hypersign.id/resources/blog/best-aadhaar-verification-api-providers)
- [Hackingly](https://www.hackingly.in/about-us) · [RevRag.ai](https://www.revrag.ai/about)
