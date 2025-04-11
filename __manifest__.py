{
    'name': 'Odoo Chat LLM',
    'version': '1.0',
    'category': 'Website',
    'summary': 'Chat with your Odoo database using RAG-enhanced LLM',
    'description': """
        This module provides a chat interface that uses Groq's LLM API to interact with your Odoo database.
        It implements RAG (Retrieval-Augmented Generation) to provide more accurate and context-aware responses.
    """,
    'author': 'Your Name',
    'website': 'https://www.yourwebsite.com',
    'depends': ['base', 'web', 'website', 'sale', 'product'],
    'data': [
        'data/website_menu.xml',
        'views/website_chat_template.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
