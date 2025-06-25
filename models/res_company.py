# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'
    sale_discount_product_id = fields.Many2one(
        comodel_name='product.product',
        string="Discount Product",
        domain=[
            ('type', 'in', ['service', 'product']),
            ('invoice_policy', '=', 'order'),
        ],
        help="Default product used for discounts",
        check_company=True,
    )

    sale_down_payment_product_id = fields.Many2one(
        comodel_name='product.product',
        string="Deposit Product",
        domain=[
            ('type', 'in', ['service', 'product']),
            ('invoice_policy', '=', 'order'),
        ],
        help="Default product used for down payments",
        check_company=True,
    )