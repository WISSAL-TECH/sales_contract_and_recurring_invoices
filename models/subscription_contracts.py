# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import api, fields, models
from odoo.tools import date_utils
from odoo.tools.safe_eval import datetime


class SubscriptionContracts(models.Model):
    """ Model for subscription contracts """
    _name = 'subscription.contracts'
    _description = 'Subscription Contracts'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom de Contrat',default="/",
                       help='Name of Contract')
    type = fields.Selection([
        ('convention', 'Convention'),
        ('facilite', 'Facilité'),
    ],string='Type de contrat')

    partner_id = fields.Many2one('res.partner', string="Customer",
                                 help='Customer for this contract')
    recurring_period = fields.Selection([
        ('12', '12'),
        ('18', '18'),
        ('24', '24'),
    ], string='Période récurrente',
        help='Recurring period of '
             'subscription contract')
    total_margin = fields.Float(string='Total Margin', compute='_compute_total_margin')

    recurring_period_interval = fields.Selection([
        ('Days', 'Jours'),
        ('Weeks', 'Semaine'),
        ('Months', 'Mois'),
        ('Years', 'Ans'),
    ],default="Months", help='Recurring interval of subscription contract')
    contract_reminder = fields.Integer(
        string='Rappel d\'expiration du contrat (Jours)',
        help='Expiry reminder of subscription contract in days.')
    recurring_invoice = fields.Integer(
        string='Intervalle de facturation récurrente (Jours)',
        help='Recurring invoice interval in days')
    next_invoice_date = fields.Date(string='Date de la prochaine facture', store=True,
                                    compute='_compute_next_invoice_date',
                                    help='Date of next invoice')
    company_id = fields.Many2one('res.company', string='Société',
                                 default=lambda self: self.env.company)

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        required=True, default=lambda self: self.env.company.currency_id)
    date_start = fields.Date(string='Date de début', default=fields.Date.today(),
                             help='Subscription contract start date')
    invoice_count = fields.Integer(store=True,
                                   compute='_compute_invoice_count',
                                   string='Numero de facture',
                                   help='Number of invoices generated')
    date_end = fields.Date(string='Date de fin', help='Subscription End Date')
    current_reference = fields.Integer(compute='_compute_sale_order_lines',
                                       string='Identifiant de l\'abonnement actuel',
                                       help='Current Subscription id')
    lock = fields.Boolean(string='verrouiller', default=False,
                          help='Lock subscription contract so that further'
                               ' modifications are not possible.')
    state = fields.Selection([
        ('New', 'Nouveau'),
        ('Ongoing', 'En cours'),
        ('Expire Soon', 'Expire bientôt'),
        ('Expired', 'Expiré'),
        ('Cancelled', 'Annulé'),
    ], string='Stage', default='New', copy=False, tracking=True,
        readonly=True, help='Status of subscription contract')
    contract_line_ids = fields.One2many(
        'subscription.contracts.line',
        'subscription_contract_id',
        string='Lignes', help='Products to be added in the contract')
    amount_total = fields.Monetary(string="Total", store=True,
                                   compute='_compute_amount_total', tracking=4,
                                   help='Total amount')
    sale_order_line_ids = fields.One2many(
        'sale.order.line', 'contract_id',
        string='Lignes de commande',
        help='Order lines of Sale Orders which belongs to this contract')
    note = fields.Html(string="Termes et conditions",
                       help='Add any notes', translate=True)
    invoices_active = fields.Boolean(
        'Facture active', default=False,
        compute='_compute_invoice_active',
        help='Compute invoices are active or not')

    def action_to_confirm(self):
        """ Confirm the Contract """
        self.write({'state': 'Ongoing'})

    def action_to_cancel(self):
        """ Cancel the Contract """
        self.write({'state': 'Cancelled'})

    def action_generate_invoice(self):
        """ Generate invoice """
        self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'invoice_date': fields.date.today(),
                'contract_origin': self.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.description,
                    'quantity': line.qty_ordered,
                    'price_unit': line.price_unit,
                    'tax_ids': line.tax_ids,
                    'discount': line.discount,
                }) for line in self.contract_line_ids]
            })
        self.invoice_count = self.env['account.move'].search_count([
            ('contract_origin', '=', self.id)])

    def action_lock(self):
        """ Lock subscription contract """
        self.lock = True

    def action_to_unlock(self):
        """ Unlock subscription contract """
        self.lock = False

    def action_get_invoice(self):
        """ Access generated invoices """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'domain': [('contract_origin', '=', self.id)],
        }

    @api.depends('contract_line_ids.sub_total')
    def _compute_amount_total(self):
        """ Compute total amount of Contract """
        for order in self:
            order_lines = order.contract_line_ids
            order.amount_total = sum(order_lines.mapped('sub_total'))

    def apply_discount_on_lines(self):
        for order in self:
            if order.recurring_period == '12' and self.company_id.marge_12:
                for line in order.contract_line_ids:
                    line.discount = self.company_id.marge_12
            if order.recurring_period == '18' and self.company_id.marge_18:
                for line in order.contract_line_ids:
                    line.discount = self.company_id.marge_18
            if order.recurring_period == '24' and self.company_id.marge_24:
                for line in order.contract_line_ids:
                    line.discount = self.company_id.marge_24

    @api.depends('partner_id')
    def _compute_invoice_count(self):
        """ Compute the count of invoices generated """
        self.invoice_count = self.env['account.move'].search_count([
            ('contract_origin', '=', self.id)
        ])

    @api.depends('invoices_active')
    def _compute_invoice_active(self):
        """ Check invoice count to display the invoice smart button """
        invoice_count = self.env['account.move'].search_count([
            ('contract_origin', '=', self.id)
        ])
        if invoice_count != 0:
            self.invoices_active = True
        else:
            self.invoices_active = False

    @api.depends('date_start', 'recurring_invoice', 'recurring_period',
                 'recurring_period_interval')
    def _compute_next_invoice_date(self):
        """ Compute next invoice date of contract """
        self.next_invoice_date = fields.Date.today()
        start_date = self.date_start
        interval = self.recurring_invoice
        recurring_period = int(self.recurring_period or 0)
        recurring_period_interval = self.recurring_period_interval
        self.next_invoice_date = date_utils.add(start_date,
                                                days=int(interval))
        if recurring_period_interval == 'Days':
            next_schedule = date_utils.add(start_date,
                                           days=int(recurring_period))
            self.date_end = next_schedule
        elif recurring_period_interval == 'Weeks':
            next_schedule = date_utils.add(start_date,
                                           weeks=int(recurring_period))
            self.date_end = next_schedule
        elif recurring_period_interval == 'Months':
            next_schedule = date_utils.add(start_date,
                                           months=int(recurring_period))
            self.date_end = next_schedule
        else:
            next_schedule = date_utils.add(start_date,
                                           years=int(recurring_period))
            self.date_end = next_schedule

    @api.model
    def subscription_contract_state_change(self):
        """ Automatic state change and create invoice """
        records = self.env['subscription.contracts'].search([])
        for rec in records:
            end_date = rec.date_end
            expiry_reminder = rec.contract_reminder
            expiry_warning_date = date_utils.subtract(end_date,
                                                      days=int(
                                                          expiry_reminder))
            current_date = fields.Date.today()
            next_invoice_date = rec.next_invoice_date
            if expiry_warning_date <= current_date <= end_date:
                rec.write({'state': 'Expire Soon'})
            if end_date < current_date:
                rec.write({'state': 'Expired'})
            if next_invoice_date == current_date and rec.state != 'Cancelled':
                data = rec.env['account.move'].create([
                    {
                        'move_type': 'out_invoice',
                        'partner_id': rec.partner_id.id,
                        'invoice_date': fields.date.today(),
                        'contract_origin': rec.id,
                    }])
                for line in rec.contract_line_ids:
                    data.write({
                        'invoice_line_ids': [(0, 0, {
                            'product_id': line.product_id.id,
                            'name': line.description,
                            'quantity': line.qty_ordered,
                            'price_unit': line.price_unit,
                            'tax_ids': line.tax_ids,
                            'discount': line.discount,
                        })],
                    })
                rec.invoice_count = rec.env['account.move'].search_count([
                    ('contract_origin', '=', rec.id)])

    @api.depends('current_reference')
    def _compute_sale_order_lines(self):
        """ Get sale order line of contract lines """
        self.current_reference = self.id
        product_id = self.contract_line_ids.mapped('product_id')
        sale_order_line = self.env['sale.order.line'].search([
            ('order_partner_id', '=', self.partner_id.id)
        ])
        for rec in sale_order_line:
            if self.date_start <= datetime.datetime.date(
                    rec.create_date) <= self.date_end:
                if rec.product_id in product_id:
                    rec.contract_id = self.id


    @api.model
    def create(self, vals):
        
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('sequence_subscription_contracts') or '/'


        res = super(SubscriptionContracts, self).create(vals)

        return res
