from odoo import api, fields, models, _
from odoo.osv import expression
from odoo.tools.sql import column_exists, create_column



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # used to know if generate a task and/or a project, depending on the product settings
    is_service = fields.Boolean("Is a Service", compute='_compute_is_service', store=True, compute_sudo=True)

    @api.depends('product_id.type')
    def _compute_is_service(self):
        for so_line in self:
            so_line.is_service = so_line.product_id.type in ['service', 'product']

    def _auto_init(self):
        """
        Create column to stop ORM from computing it himself (too slow)
        """
        if not column_exists(self.env.cr, 'sale_order_line', 'is_service'):
            create_column(self.env.cr, 'sale_order_line', 'is_service', 'bool')
            self.env.cr.execute("""
                    UPDATE sale_order_line line
                    SET is_service = (pt.type in ['service','product'])
                    FROM product_product pp
                    LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE pp.id = line.product_id
                """)
        return super()._auto_init()

    @api.depends('is_expense', 'product_id.type', 'product_id.service_type')
    def _compute_qty_delivered_method(self):
        for line in self:
            if line.is_expense:
                line.qty_delivered_method = 'analytic'
            elif line.product_id and line.product_id.type in ['service','product'] and line.product_id.service_type == 'timesheet':
                line.qty_delivered_method = 'timesheet'
            else:
                line.qty_delivered_method = 'manual'

    def _get_product_from_sol_name_domain(self, product_name):
        return [
            ('name', 'ilike', product_name),
            '|',
            ('type', '=', 'service'),
            ('type', '=', 'product'),
            ('company_id', 'in', [False, self.env.company.id]),
        ]

    @api.depends('product_id.type')
    def _compute_product_updatable(self):
        super()._compute_product_updatable()
        for line in self:
            if (line.product_id.type in ['service', 'product']) and line.state == 'sale':
                line.product_updatable = False

    @api.depends('product_id')
    def _compute_qty_delivered_method(self):
        milestones_lines = self.filtered(lambda sol:
                                         not sol.is_expense
                                         and (sol.product_id.type in ['service', 'product'])
                                         and sol.product_id.service_type == 'milestones'
                                         )
        milestones_lines.qty_delivered_method = 'milestones'
        super(SaleOrderLine, self - milestones_lines)._compute_qty_delivered_method()

    def write(self, values):
        result = super().write(values)
        # changing the ordered quantity should change the allocated hours on the
        # task, whatever the SO state. It will be blocked by the super in case
        # of a locked sale order.
        if 'product_uom_qty' in values and not self.env.context.get('no_update_allocated_hours', False):
            for line in self:
                if line.task_id and (line.product_id.type in ['service', 'product']):
                    allocated_hours = line._convert_qty_company_hours(line.task_id.company_id or self.env.user.company_id)
                    line.task_id.write({'allocated_hours': allocated_hours})
        return result

    def _timesheet_create_project_prepare_values(self):
        """Generate project values"""
        account = self.order_id.analytic_account_id
        if not account:
            service_products = self.order_id.order_line.mapped('product_id').filtered(
                lambda p: p.type in ('service', 'product') and p.default_code
            )
            default_code = service_products.default_code if len(service_products) == 1 else None
            self.order_id._create_analytic_account(prefix=default_code)
            account = self.order_id.analytic_account_id
        # create the project or duplicate one
        return {
            'name': '%s - %s' % (self.order_id.client_order_ref,
                                 self.order_id.name) if self.order_id.client_order_ref else self.order_id.name,
            'analytic_account_id': account.id,
            'partner_id': self.order_id.partner_id.id,
            'sale_line_id': self.id,
            'active': True,
            'company_id': self.company_id.id,
            'allow_billable': True,
            'user_id': self.product_id.project_template_id.user_id.id,
        }

    def _get_so_lines_task_global_project(self):
        return self.filtered(lambda sol: sol.product_id.type in ['service',
        'product'] and sol.product_id.service_tracking == 'task_global_project')

    def _get_so_lines_new_project(self):
        return self.filtered(
            lambda sol: sol.product_id.type in ['service', 'product'] and sol.product_id.service_tracking in [
                'project_only', 'task_in_project'])


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('display_type') or self.default_get(['display_type']).get('display_type'):
                vals['product_uom_qty'] = 0.0
        lines = super().create(vals_list)
        if self.env.context.get('sale_no_log_for_new_lines'):
            return lines
        for line in lines:
            if line.product_id and line.state == 'sale':
                msg = _("Extra line with %s", line.product_id.display_name)
                line.order_id.message_post(body=msg)
                if (line.product_id.expense_policy not in [False, 'no'] or
                    (line.product_id.type in ['service', 'product'] and
                     line.product_id.service_type == 'timesheet')) and not line.order_id.analytic_account_id:
                    line.order_id._create_analytic_account()
        return lines

    @api.depends('product_id')
    def _compute_qty_delivered_method(self):
        """ Sale Timesheet module compute delivered qty for product [('type', 'in', ['service']), ('service_type', '=', 'timesheet')] """
        super(SaleOrderLine, self)._compute_qty_delivered_method()
        for line in self:
            if not line.is_expense and line.product_id.type in ['service','product'] and line.product_id.service_type == 'timesheet':
                line.qty_delivered_method = 'timesheet'

    def _timesheet_create_project(self):
        project = super()._timesheet_create_project()
        project_uom = self.company_id.project_time_mode_id
        uom_unit = self.env.ref('uom.product_uom_unit')
        uom_hour = self.env.ref('uom.product_uom_hour')

        # dict of inverse factors for each relevant UoM found in SO
        factor_inv_per_id = {
            uom.id: uom.factor_inv
            for uom in self.order_id.order_line.product_uom
            if uom.category_id == project_uom.category_id
        }
        # if sold as units, assume hours for time allocation
        factor_inv_per_id[uom_unit.id] = uom_hour.factor_inv

        allocated_hours = 0.0
        # method only called once per project, so also allocate hours for
        # all lines in SO that will share the same project
        for line in self.order_id.order_line:
            if line.is_service \
                    and line.product_id.service_tracking in ['task_in_project', 'project_only'] \
                    and line.product_id.project_template_id == self.product_id.project_template_id \
                    and line.product_uom.id in factor_inv_per_id:
                uom_factor = project_uom.factor * factor_inv_per_id[line.product_uom.id]
                allocated_hours += line.product_uom_qty * uom_factor

        # Custom name formatting: SOname - Customer : Product
        new_project_name = f"{self.order_id.name} - {self.order_id.partner_id.name}"
        project.write({
            'allocated_hours': allocated_hours,
            'allow_timesheets': True,
            'name': new_project_name,
        })

        return project

    def _recompute_qty_to_invoice(self, start_date, end_date):
        """ Recompute the qty_to_invoice field for product containing timesheets

            Search the existed timesheets between the given period in parameter.
            Retrieve the unit_amount of this timesheet and then recompute
            the qty_to_invoice for each current product.

            :param start_date: the start date of the period
            :param end_date: the end date of the period
        """
        lines_by_timesheet = self.filtered(lambda sol: sol.product_id and sol.product_id._is_delivered_timesheet())
        domain = lines_by_timesheet._timesheet_compute_delivered_quantity_domain()
        refund_account_moves = self.order_id.invoice_ids.filtered(lambda am: am.state == 'posted' and am.move_type == 'out_refund').reversed_entry_id
        timesheet_domain = [
            '|',
            ('timesheet_invoice_id', '=', False),
            ('timesheet_invoice_id.state', '=', 'cancel')]
        if refund_account_moves:
            credited_timesheet_domain = [('timesheet_invoice_id.state', '=', 'posted'), ('timesheet_invoice_id', 'in', refund_account_moves.ids)]
            timesheet_domain = expression.OR([timesheet_domain, credited_timesheet_domain])
        domain = expression.AND([domain, timesheet_domain])
        if start_date:
            domain = expression.AND([domain, [('date', '>=', start_date)]])
        if end_date:
            domain = expression.AND([domain, [('date', '<=', end_date)]])
        mapping = lines_by_timesheet.sudo()._get_delivered_quantity_by_analytic(domain)

        for line in lines_by_timesheet:
            qty_to_invoice = mapping.get(line.id, 0.0)
            if qty_to_invoice:
                line.qty_to_invoice = qty_to_invoice
            else:
                prev_inv_status = line.invoice_status
                line.qty_to_invoice = qty_to_invoice
                line.invoice_status = prev_inv_status

    def _get_action_per_item(self):
        """ Get action per Sales Order Item

            When the Sales Order Item contains a service product then the action will be View Timesheets.

            :returns: Dict containing id of SOL as key and the action as value
        """
        action_per_sol = super()._get_action_per_item()
        timesheet_action = self.env.ref('sale_timesheet.timesheet_action_from_sales_order_item').id
        timesheet_ids_per_sol = {}
        if self.user_has_groups('hr_timesheet.group_hr_timesheet_user'):
            timesheet_read_group = self.env['account.analytic.line']._read_group([('so_line', 'in', self.ids), ('project_id', '!=', False)], ['so_line'], ['id:array_agg'])
            timesheet_ids_per_sol = {so_line.id: ids for so_line, ids in timesheet_read_group}
        for sol in self:
            timesheet_ids = timesheet_ids_per_sol.get(sol.id, [])
            if sol.is_service and len(timesheet_ids) > 0:
                action_per_sol[sol.id] = timesheet_action, timesheet_ids[0] if len(timesheet_ids) == 1 else False
        return action_per_sol