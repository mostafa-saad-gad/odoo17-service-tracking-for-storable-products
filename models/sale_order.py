from odoo import api, models,fields, _
from odoo.exceptions import UserError
import ast
from odoo.osv.expression import AND
from odoo.tools import float_compare



class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sequence_only_name = fields.Char(string='Sequence Only', compute='_compute_sequence_only_name', store=False)

    @api.depends('name')
    def _compute_sequence_only_name(self):
        for order in self:
            if order.name:
                # Split at the first '-' and take the first part
                order.sequence_only_name = order.name.split('-', 1)[0]
            else:
                order.sequence_only_name = ''

    def _compute_show_project_and_task_button(self):
        is_project_manager = self.env.user.has_group('project.group_project_manager')

        # Use the public read_group method (not _read_group)
        grouped_data = self.env['sale.order.line'].read_group(
            domain=[
                ('order_id', 'in', self.ids),
                ('order_id.state', 'not in', ['draft', 'sent']),
                ('product_id.detailed_type', 'in', ['service', 'product']),
            ],
            fields=['order_id'],
            groupby=['order_id']
        )

        show_button_ids = {data['order_id'][0] for data in grouped_data if data['order_id']}

        for order in self:
            order.show_project_button = order.id in show_button_ids and bool(order.project_count)
            order.show_task_button = order.show_project_button or bool(order.tasks_count)

            eligible_templates = order.order_line.mapped('product_template_id').filtered(
                lambda x: x.service_policy in ['delivered_timesheet', 'delivered_milestones']
            )
            order.show_create_project_button = (
                    is_project_manager and
                    order.id in show_button_ids and
                    not order.project_count and
                    bool(eligible_templates)
            )


    def action_view_task(self):
        self.ensure_one()
        if not self.order_line:
            return {'type': 'ir.actions.act_window_close'}

        list_view_id = self.env.ref('project.view_task_tree2').id
        form_view_id = self.env.ref('project.view_task_form2').id
        kanban_view_id = self.env.ref('project.view_task_kanban_inherit_view_default_project').id

        action = self.env["ir.actions.actions"]._for_xml_id("project.action_view_task")
        if self.tasks_count > 1:  # cross project kanban task
            for idx, (view_id, view_type) in enumerate(action['views']):
                if view_type == 'kanban':
                    action['views'][idx] = (kanban_view_id, 'kanban')
                elif view_type == 'tree':
                    action['views'][idx] = (list_view_id, 'tree')
                elif view_type == 'form':
                    action['views'][idx] = (form_view_id, 'form')
        else:  # 1 or 0 tasks -> form view
            action['views'] = [(form_view_id, 'form')]
            action['res_id'] = self.tasks_ids.id
        # set default project
        default_line = next((sol for sol in self.order_line if sol.product_id.detailed_type in ['service','product']), self.env['sale.order.line'])
        default_project_id = default_line.project_id.id or self.project_id.id or self.project_ids[:1].id or self.tasks_ids.project_id[:1].id

        action['context'] = {
            'default_sale_order_id': self.id,
            'default_sale_line_id': default_line.id,
            'default_partner_id': self.partner_id.id,
            'default_project_id': default_project_id,
            'default_user_ids': [self.env.uid],
        }
        action['domain'] = AND([ast.literal_eval(action['domain']), self._tasks_ids_domain()])
        return action

    def action_create_project(self):
        self.ensure_one()
        if not self.order_line:
            return {'type': 'ir.actions.act_window_close'}

        sorted_line = self.order_line.sorted('sequence')
        default_sale_line = next(sol for sol in sorted_line if sol.product_id.detailed_type in ['service','product'])
        return {
            **self.env["ir.actions.actions"]._for_xml_id("project.open_create_project"),
            'context': {
                'default_sale_order_id': self.id,
                'default_sale_line_id': default_sale_line.id,
                'default_partner_id': self.partner_id.id,
                'default_user_ids': [self.env.uid],
                'default_allow_billable': 1,
                'hide_allow_billable': True,
                'default_company_id': self.company_id.id,
                'generate_milestone': default_sale_line.product_id.service_policy == 'delivered_milestones',
            },
        }

    def action_view_project_ids(self):
        self.ensure_one()
        if not self.order_line:
            return {'type': 'ir.actions.act_window_close'}

        sorted_line = self.order_line.sorted('sequence')
        default_sale_line = next((sol for sol in sorted_line if sol.product_id.detailed_type in ['service','product']), None)

        action = {
            'type': 'ir.actions.act_window',
            'name': _('Projects'),
            'domain': ['|', ('sale_order_id', '=', self.id), ('id', 'in', self.with_context(active_test=False).project_ids.ids), ('active', 'in', [True, False])],
            'res_model': 'project.project',
            'views': [(False, 'kanban'), (False, 'tree'), (False, 'form')],
            'view_mode': 'kanban,tree,form',
            'context': {
                **self._context,
                'default_partner_id': self.partner_id.id,
                'default_sale_line_id': default_sale_line.id if default_sale_line else False,
                'default_allow_billable': 1,
            }
        }
        if len(self.with_context(active_test=False).project_ids) == 1:
            action.update({'views': [(False, 'form')], 'res_id': self.project_ids.id})
        return action

    def _get_order_with_valid_service_product(self):
        # Modified to include all product types
        groups = self.env['sale.order.line'].read_group(
            domain=[
                ('order_id', 'in', self.ids),
                ('order_id.state', '=', 'sale'),
                ('product_id.type', 'in', ['service', 'product']),
            ],
            fields=['order_id'],
            groupby=['order_id']
        )
        return [g['order_id'][0] for g in groups]

    def _get_prepaid_service_lines_to_upsell(self):
        """ Retrieve all sols which need to display an upsell activity warning in the SO

            Modified to include all product types with ordered_prepaid policy
        """
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        return self.order_line.filtered(lambda sol:
                                        sol.product_id.type in ['service', 'product']
                                        and sol.invoice_status != "invoiced"
                                        and not sol.has_displayed_warning_upsell
                                        and sol.product_id.service_policy == 'ordered_prepaid'
                                        and float_compare(
                                            sol.qty_delivered,
                                            sol.product_uom_qty * (sol.product_id.service_upsell_threshold or 1.0),
                                            precision_digits=precision
                                        ) > 0
                                        )


    from odoo import fields  # Make sure this is imported

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                self = self.with_company(vals['company_id'])

            # Generate name if "New"
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_order'])
                ) if 'date_order' in vals else None

                seq = self.env['ir.sequence'].next_by_code(
                    'sale.order', sequence_date=seq_date
                ) or _("New")

                partner_name = ''
                if 'partner_id' in vals:
                    partner = self.env['res.partner'].browse(vals['partner_id'])
                    partner_name = partner.name or ''

                vals['name'] = f"{seq}-{partner_name}" if partner_name else seq

        created_records = super().create(vals_list)

        # Handle project sale_line_id assignment
        project = self.env['project.project'].browse(self.env.context.get('create_for_project_id'))
        if project:
            for order in created_records:
                valid_sol = next(
                    (sol for sol in order.order_line if sol.product_id.type in ['service', 'product']), False)
                if not valid_sol:
                    raise UserError(_('This Sales Order must contain at least one product of type "Service" or "Product".'))
                if not project.sale_line_id:
                    project.sale_line_id = valid_sol

        return created_records