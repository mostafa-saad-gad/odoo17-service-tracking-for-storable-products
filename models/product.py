from odoo import api, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends('invoice_policy', 'service_type', 'type')
    def _compute_service_policy(self):
        for product in self:
            product.service_policy = self._get_general_to_service(product.invoice_policy, product.service_type)
            if not product.service_policy and product.type in ['service', 'product']:
                product.service_policy = 'ordered_prepaid'

    @api.depends('service_tracking', 'service_policy', 'type', 'sale_ok')
    def _compute_product_tooltip(self):
        super()._compute_product_tooltip()
        for record in self.filtered(lambda record: record.type in ['service', 'product'] and record.sale_ok):
            if record.service_policy == 'ordered_prepaid':
                if record.service_tracking == 'no':
                    record.product_tooltip = _(
                        "Invoice ordered quantities as soon as this service is sold."
                    )
                elif record.service_tracking == 'task_global_project':
                    record.product_tooltip = _(
                        "Invoice ordered quantities as soon as this service is sold. "
                        "Create a task in an existing project to track the time spent."
                    )
                elif record.service_tracking == 'project_only':
                    record.product_tooltip = _(
                        "Invoice ordered quantities as soon as this service is sold. "
                        "Create an empty project for the order to track the time spent."
                    )
                elif record.service_tracking == 'task_in_project':
                    record.product_tooltip = _(
                        "Invoice ordered quantities as soon as this service is sold. "
                        "Create a project for the order with a task for each sales order line "
                        "to track the time spent."
                    )
            elif record.service_policy == 'delivered_milestones':
                if record.service_tracking == 'no':
                    record.product_tooltip = _(
                        "Invoice your milestones when they are reached."
                    )
                elif record.service_tracking == 'task_global_project':
                    record.product_tooltip = _(
                        "Invoice your milestones when they are reached. "
                        "Create a task in an existing project to track the time spent."
                    )
                elif record.service_tracking == 'project_only':
                    record.product_tooltip = _(
                        "Invoice your milestones when they are reached. "
                        "Create an empty project for the order to track the time spent."
                    )
                elif record.service_tracking == 'task_in_project':
                    record.product_tooltip = _(
                        "Invoice your milestones when they are reached. "
                        "Create a project for the order with a task for each sales order line "
                        "to track the time spent."
                    )
            elif record.service_policy == 'delivered_manual':
                if record.service_tracking == 'no':
                    record.product_tooltip = _(
                        "Invoice this service when it is delivered (set the quantity by hand on your sales order lines). "
                    )
                elif record.service_tracking == 'task_global_project':
                    record.product_tooltip = _(
                        "Invoice this service when it is delivered (set the quantity by hand on your sales order lines). "
                        "Create a task in an existing project to track the time spent."
                    )
                elif record.service_tracking == 'project_only':
                    record.product_tooltip = _(
                        "Invoice this service when it is delivered (set the quantity by hand on your sales order lines). "
                        "Create an empty project for the order to track the time spent."
                    )
                elif record.service_tracking == 'task_in_project':
                    record.product_tooltip = _(
                        "Invoice this service when it is delivered (set the quantity by hand on your sales order lines). "
                        "Create a project for the order with a task for each sales order line "
                        "to track the time spent."
                    )

    @api.onchange('service_policy')
    def _inverse_service_policy(self):
        for product in self:
            if product.service_policy and product.type in ['service', 'product']:
                product.invoice_policy, product.service_type = self._get_service_to_general(product.service_policy)

    @api.onchange('type')
    def _onchange_type(self):
        print(self.type)
        res = super(ProductTemplate, self)._onchange_type()
        if self.type != 'service' and self.type != 'product':
            self.service_tracking = 'no'
        return res

    def write(self, vals):
        if 'type' in vals and ((vals['type'] != 'service' and vals['type'] != 'product')):
            vals.update({
                'service_tracking': 'no',
                'project_id': False
            })
        return super(ProductTemplate, self).write(vals)

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.onchange('service_policy')
    def _inverse_service_policy(self):
        for product in self:
            if product.service_policy and product.type in ['service', 'product']:
                product.invoice_policy, product.service_type = self._get_service_to_general(product.service_policy)


    @api.onchange('type')
    def _onchange_type(self):
        print(self.type)
        res = super(ProductProduct, self)._onchange_type()
        if (self.type != 'service' and self.type != 'product'):
            self.service_tracking = 'no'
        return res

    def write(self, vals):
        if 'type' in vals and (vals['type'] != 'service' and vals['type'] != 'product'):
            vals.update({
                'service_tracking': 'no',
                'project_id': False
            })
        return super(ProductProduct, self).write(vals)

    def _is_delivered_timesheet(self):
        """ Check if the product is a delivered timesheet """
        self.ensure_one()
        return self.type in ['service','product'] and self.service_policy == 'delivered_timesheet'

    @api.onchange('type', 'service_type', 'service_policy')
    def _onchange_service_fields(self):
        for record in self:
            default_uom_id = self.env['ir.default']._get_model_defaults('product.product').get('uom_id')
            default_uom = self.env['uom.uom'].browse(default_uom_id)
            if record.type in ['service','product'] and record.service_type == 'timesheet' and \
                    not (record._origin.service_policy and record.service_policy == record._origin.service_policy):
                if default_uom and default_uom.category_id == self.env.ref('uom.uom_categ_wtime'):
                    record.uom_id = default_uom
                else:
                    record.uom_id = self.env.ref('uom.product_uom_hour')
            elif record._origin.uom_id:
                record.uom_id = record._origin.uom_id
            elif default_uom:
                record.uom_id = default_uom
            else:
                record.uom_id = self._get_default_uom_id()
            record.uom_po_id = record.uom_id

