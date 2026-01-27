# -*- coding: utf-8 -*-
from odoo import fields, models
class PrinterPrint(models.Model):
    """This class is created for model printer.details. It contains fields for the model"""
    _name = "printer.details"
    _description = "Printer Details"
    _rec_name = 'printers_name'

    id_of_printer = fields.Char(string="Printer ID", help="id of printer")
    printers_name = fields.Char(string="Printer Name", help="name of printer")
    printer_description = fields.Char(string="Printer Description", help="description of printer")
    state = fields.Char(string="Status", help="status of printer")
