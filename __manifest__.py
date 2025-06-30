{
    'name': 'Storable Product as Service',
    'version': '17.0.1.0.0',
    'summary' : 'Add a product service feature',
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
    ],
'images': [
        'static/description/icon.png',
        'static/description/project_task.jpg',
        'static/description/sale_order_item.jpg',
        'static/description/storable_product.jpg',
        'static/description/analytic_account.jpg',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}