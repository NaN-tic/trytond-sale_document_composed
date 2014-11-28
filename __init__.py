# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .sale import *


def register():
    Pool.register(
        Configuration,
        ConfigurationDocument,
        SaleLine,
        PrintDocumentWarning,
        module='sale_document_composed', type_='model')
    Pool.register(
        PrintDocument,
        module='sale_document_composed', type_='wizard')
    Pool.register(
        DocumentTitleReport,
        DocumentIndexReport,
        DocumentDetailReport,
        DocumentReport,
        module='sale_document_composed', type_='report')
