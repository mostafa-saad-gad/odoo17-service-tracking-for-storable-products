from odoo import api, models, _
from odoo.osv import expression
from odoo.tools.misc import unquote

TIMESHEET_INVOICE_TYPES = [
    ('billable_time', 'Billed on Timesheets'),
    ('billable_fixed', 'Billed at a Fixed price'),
    ('billable_milestones', 'Billed on Milestones'),
    ('billable_manual', 'Billed Manually'),
    ('non_billable', 'Non Billable Tasks'),
    ('timesheet_revenues', 'Timesheet Revenues'),
    ('service_revenues', 'Service Revenues'),
    ('other_revenues', 'Other revenues'),
    ('other_costs', 'Other costs'),
]

class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    def _domain_so_line(self):
        domain = expression.AND([
            self.env['sale.order.line']._sellable_lines_domain(),
            [
                ('qty_delivered_method', 'in', ['analytic', 'timesheet']),
                ('is_expense', '=', False),
                ('state', '=', 'sale'),
                ('order_partner_id.commercial_partner_id', '=', unquote('commercial_partner_id')),
            ],
        ])
        return str(domain)

    def _default_sale_line_domain(self):
        # [XBO] TODO: remove me in master
        return expression.OR([[
            ('is_expense', '=', False),
            ('state', '=', 'sale'),
            ('order_partner_id', 'child_of', self.sudo().commercial_partner_id.ids)
        ], super()._default_sale_line_domain()])

    @api.depends('so_line.product_id', 'project_id.billing_type', 'amount')
    def _compute_timesheet_invoice_type(self):
        for timesheet in self:
            if timesheet.project_id:  # AAL will be set to False
                invoice_type = False
                if not timesheet.so_line:
                    invoice_type = 'non_billable' if timesheet.project_id.billing_type != 'manually' else 'billable_manual'
                elif timesheet.so_line.product_id.type in ['service', 'product']:
                    if timesheet.so_line.product_id.invoice_policy == 'delivery':
                        if timesheet.so_line.product_id.service_type == 'timesheet':
                            invoice_type = 'timesheet_revenues' if timesheet.amount > 0 else 'billable_time'
                        else:
                            service_type = timesheet.so_line.product_id.service_type
                            invoice_type = f'billable_{service_type}' if service_type in ['milestones',
                                                                                          'manual'] else 'billable_fixed'
                    elif timesheet.so_line.product_id.invoice_policy == 'order':
                        invoice_type = 'billable_fixed'
                timesheet.timesheet_invoice_type = invoice_type
            else:
                if timesheet.amount >= 0:
                    if timesheet.so_line and timesheet.so_line.product_id.type in ['service', 'product']:
                        timesheet.timesheet_invoice_type = 'service_revenues'
                    else:
                        timesheet.timesheet_invoice_type = 'other_revenues'
                else:
                    timesheet.timesheet_invoice_type = 'other_costs'

