# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import tempfile
import os
import subprocess
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, \
    Button
from trytond.modules.jasper_reports.jasper import JasperReport
from PyPDF2 import PdfFileReader, PdfFileWriter
from io import BytesIO

__all__ = ['Configuration', 'ConfigurationDocument', 'SaleLine',
    'PrintDocumentWarning', 'PrintDocument', 'DocumentTitleReport',
    'DocumentIndexReport', 'DocumentDetailReport', 'DocumentReport']
__metaclass__ = PoolMeta


class Configuration:
    __name__ = 'sale.configuration'
    documents = fields.One2Many('sale.configuration.document', 'configuration',
        'Documents')
    composition_page = fields.Binary('Composition Page')


class ConfigurationDocument(ModelSQL, ModelView):
    'Sale Configuration Document'
    __name__ = 'sale.configuration.document'
    configuration = fields.Many2One('sale.configuration', 'Configuration',
        required=True)
    name = fields.Char('Name', required=True)
    content = fields.Binary('Content', required=True)


class SaleLine:
    __name__ = 'sale.line'
    attachment_resource = fields.Function(fields.Char('Attachment Resource'),
        'on_change_with_attachment_resource')
    attachment = fields.Many2One('ir.attachment', 'Document',
        domain=[
            ('resource', '=', Eval('attachment_resource')),
            ],
        states={
            'invisible': Eval('type') != 'line',
            },
        context={
            'resource': Eval('attachment_resource'),
            },
        depends=['attachment_resource', 'type'])
    document = fields.Many2One('sale.configuration.document', 'Document',
        states={
        'invisible': Eval('type') != 'pdf',
        'required': Eval('type') == 'pdf',
        },
        depends=['type'])

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        value = ('pdf', 'PDF')
        if value not in cls.type.selection:
            cls.type.selection.append(value)

    @fields.depends('product')
    def on_change_with_attachment_resource(self, name=None):
        if self.product:
            return 'product.template,' + str(self.product.template.id)
        return 'product.template,-1'

    @fields.depends('document')
    def on_change_document(self):
        if self.document:
            self.description = self.document.name


class PrintDocumentWarning(ModelView):
    'Print Document Warning'
    __name__ = 'sale.document.print.warning'


class PrintDocument(Wizard):
    'Print Sale Document'
    __name__ = 'sale.document.print'
    start = StateTransition()
    warning = StateView('sale.document.print.warning',
        'sale_document_composed.print_warning_view_form', [
            Button('Ok', 'end', 'tryton-cancel', default=True),
            ])
    print_ = StateAction('sale_document_composed.document_report')

    def transition_start(self):
        if len(Transaction().context['active_ids']) > 1:
            return 'warning'
        return 'print_'

    def do_print_(self, action):
        data = {}
        data['id'] = Transaction().context['active_ids'].pop()
        data['ids'] = [data['id']]
        return action, data

    def transition_print_(self):
        if Transaction().context['active_ids']:
            return 'print_'
        return 'end'


class DocumentTitleReport(JasperReport):
    __name__ = 'sale.document.title.report'


class DocumentIndexReport(JasperReport):
    __name__ = 'sale.document.index.report'


class DocumentDetailReport(JasperReport):
    __name__ = 'sale.document.detail.report'


class DocumentReport(Report):
    __name__ = 'sale.document.report'

    @classmethod
    def get_title_report(cls, ids, data):
        pool = Pool()
        Title = pool.get('sale.document.title.report', type='report')
        return Title.execute(ids, data)

    @classmethod
    def get_index_report(cls, ids, data):
        pool = Pool()
        Index = pool.get('sale.document.index.report', type='report')
        return Index.execute(ids, data)

    @classmethod
    def get_detail_report(cls, ids, data):
        pool = Pool()
        Detail = pool.get('sale.document.detail.report', type='report')
        return Detail.execute(ids, data)

    @classmethod
    def get_additional_files(cls, ids, data):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        files = []
        for line in SaleLine.search([
                    ('sale', 'in', ids),
                    ('type', 'in', ['line', 'pdf']),
                    ]):
            if line.document:
                files.append(line.document.content)
            if line.attachment:
                files.append(line.attachment.data)
        return files

    @classmethod
    def execute(cls, ids, data):
        pool = Pool()
        Config = pool.get('sale.configuration')
        ActionReport = pool.get('ir.action.report')
        config = Config.get_singleton()
        action_reports = ActionReport.search([
                ('report_name', '=', cls.__name__)
                ])
        if not action_reports:
            raise UserError('Warning', 'Report (%s) not found!' % cls.__name__)
        action_report = action_reports[0]
        # Pick only one id (as it will fail if we try to execute for more)
        if len(ids) > 1:
            ids = [ids[0]]
        title = cls.get_title_report(ids, data)
        title = title and (title[1],) or ()
        index = cls.get_index_report(ids, data)
        index = index and (index[1],) or ()
        detail = cls.get_detail_report(ids, data)
        detail = detail and (detail[1],) or ()
        additional = cls.get_additional_files(ids, data)
        additional = additional and tuple(additional) or ()
        pdfs_data = title + index + additional + detail
        pdf_data = JasperReport.merge_pdfs(pdfs_data)
        try:
            if config.composition_page:
                output = PdfFileWriter()
                orig = PdfFileReader(BytesIO(pdf_data))
                wpdf = PdfFileReader(BytesIO(
                        config.composition_page))
                watermark = wpdf.getPage(0)
                for i in xrange(orig.getNumPages()):
                    page = orig.getPage(i)
                    page.mergePage(watermark)
                    output.addPage(page)

                tmppdf = BytesIO()
                output.write(tmppdf)
                pdf_data = tmppdf.getvalue()
                tmppdf.close()

            return ('pdf', buffer(pdf_data), action_report.direct_print,
                action_report.name)
        except:
            raise UserError('Warning', 'Report (%s) not found!' % cls.__name__)
