{
    'name': 'Product Service Behavior Extension',
    'version': '17.0.1.0.0',
    'summary': 'Extends storable product functionality to behave like service products',
    'description': """
This module customizes Odoo to allow storable products (type='product') to support features typically exclusive to service products:
- Project and task creation on sales
- Timesheet tracking and invoicing
- Custom sale order naming with customer name (e.g., S00039-Customer-Name)
- Enhanced tooltip and invoice policy behavior

It extends functionality across the following core modules:
- sale
- sale_project
- sale_timesheet
- project
    """,
    'category': 'Sales',
    'author': 'Mostafa Saad',
    'depends': [
        'sale',
        'sale_project',
        'sale_timesheet',
        'project',
        'product'
    ],
    'data': [
        'views/product_views.xml',
        'views/sale_order_view.xml'
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}