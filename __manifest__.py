# -*- coding: utf-8 -*-
{
    'name': 'Survey API Helper',
    'version': '18.0.1.0.0',
    'category': 'ISD Modules',
    'summary': 'API tools to help integrate with Survey module',
    'description': """
Survey API Helper
=================

Provides tools to help developers integrate with Odoo Survey:
* List all surveys with API endpoints
* Show survey structure (questions, types, answer keys)
* Generate sample JSON payload for testing
* RESTful API endpoint to submit survey responses

Features:
---------
* Menu: Survey > API Helper
* View survey questions and field mappings
* Copy sample JSON payload to clipboard
* API endpoint: POST /api/survey/<survey_id>/submit
    """,
    'author': 'ISD Development Team',
    'website': 'https://intellisyncdata.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'survey',
        'hr',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/survey_api_helper_views.xml',
        'views/survey_survey_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
