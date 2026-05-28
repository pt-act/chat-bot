from unittest.mock import patch

import fakeredis
import pytest
from fpdf import FPDF
from langchain_chroma import Chroma

POLICY_V1 = """\
Return Policy

Customers may return any item within 30 days of purchase for a full refund.
To initiate a return, customers must contact our support team at support@company.com
and provide the original order number, proof of purchase, and a brief description
of the reason for the return. Returns without prior authorization will not be accepted.
Items must be in their original condition, unused, and in the original packaging.

Damaged or defective items must be reported within 24 hours of delivery.
Customers should photograph the damage and attach the images when contacting support.
Failure to report damage within the specified window may result in the claim being denied.
Our team will review each case individually and respond within two business days.

Refunds are processed within 5 to 7 business days after the returned item is received.
Refunds will be issued to the original payment method only. If the original payment
method is no longer available, store credit will be issued instead. Shipping fees are
non-refundable unless the return is due to our error or a defective product.

Exchange Policy

Items may be exchanged within 14 days of purchase. Original receipt required.
Exchanges are subject to product availability. If the requested item is out of stock,
customers may choose an alternative product of equal value or receive a store credit.
Exchanges must be initiated through our online portal or by visiting a physical store.

Shipping Policy

All orders are processed within 1 to 2 business days after payment confirmation.
Standard shipping takes 5 to 7 business days. Express shipping is available for an
additional fee and delivers within 2 to 3 business days. International orders may
take 10 to 20 business days depending on customs clearance in the destination country.
Customers will receive a tracking number by email once the order has been dispatched.

Privacy and Data Policy

We collect personal data only for the purpose of processing your order and improving
our services. Your data will never be sold to third parties. Customers may request
deletion of their data at any time by contacting privacy@company.com. We comply with
all applicable data protection regulations including GDPR and local privacy laws.
"""

POLICY_V2 = """\
Return Policy

Customers may return any item within 60 days of purchase for a full refund.
To initiate a return, customers must contact our support team at support@company.com
and provide the original order number, proof of purchase, and a brief description
of the reason for the return. Returns without prior authorization will not be accepted.
Items must be in their original condition, unused, and in the original packaging.

Damaged or defective items must be reported within 24 hours of delivery.
Customers should photograph the damage and attach the images when contacting support.
Failure to report damage within the specified window may result in the claim being denied.
Our team will review each case individually and respond within two business days.

Refunds are processed within 3 to 5 business days after the returned item is received.
Refunds will be issued to the original payment method only. If the original payment
method is no longer available, store credit will be issued instead. Shipping fees are
non-refundable unless the return is due to our error or a defective product.

Exchange Policy

Items may be exchanged within 14 days of purchase. Original receipt required.
Exchanges are subject to product availability. If the requested item is out of stock,
customers may choose an alternative product of equal value or receive a store credit.
Exchanges must be initiated through our online portal or by visiting a physical store.

Shipping Policy

All orders are processed within 1 to 2 business days after payment confirmation.
Standard shipping takes 5 to 7 business days. Express shipping is available for an
additional fee and delivers within 2 to 3 business days. International orders may
take 10 to 20 business days depending on customs clearance in the destination country.
Customers will receive a tracking number by email once the order has been dispatched.

Privacy and Data Policy

We collect personal data only for the purpose of processing your order and improving
our services. Your data will never be sold to third parties. Customers may request
deletion of their data at any time by contacting privacy@company.com. We comply with
all applicable data protection regulations including GDPR and local privacy laws.
"""


def _make_pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for paragraph in text.strip().split("\n\n"):
        pdf.multi_cell(0, 8, paragraph.strip())
        pdf.ln(4)
    return bytes(pdf.output())


@pytest.fixture(scope="session")
def pdf_v1_bytes():
    return _make_pdf_bytes(POLICY_V1)


@pytest.fixture(scope="session")
def pdf_v2_bytes():
    return _make_pdf_bytes(POLICY_V2)


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[float((i + 1) % 9) / 9] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.5] * 8


@pytest.fixture
def vectorstore(tmp_path):
    return Chroma(
        collection_name="test_policies",
        persist_directory=str(tmp_path / "chroma"),
        embedding_function=FakeEmbeddings(),
    )


@pytest.fixture
def ingest_env(fake_redis, vectorstore):
    with (
        patch("ingest.policies.get_redis", return_value=fake_redis),
        patch("ingest.policies.get_vectorstore", return_value=vectorstore),
    ):
        yield fake_redis, vectorstore
