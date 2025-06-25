from odoo import models
from odoo.osv import expression
from odoo.tools.misc import unquote


class ProjectProductEmployeeMap(models.Model):
    _inherit = 'project.sale.line.employee.map'

    def _domain_sale_line_id(self):
        domain = expression.AND([
            self.env['sale.order.line']._sellable_lines_domain(),
            [
                ('is_expense', '=', False),
                ('state', '=', 'sale'),
                ('order_partner_id', '=?', unquote('partner_id')),
            ],
        ])
        return domain