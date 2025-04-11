from odoo import http
from odoo.http import request
import json
import logging
from groq import Groq
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

_logger = logging.getLogger(__name__)

class RagChatController(http.Controller):
    @http.route('/rag/chat', type='http', auth='public', website=True)
    def rag_chat_page(self, **kwargs):
        return request.render('odoo_chat_llm.rag_chat_page')

    @http.route('/rag/chat/message', type='json', auth='public', website=True)
    def process_message(self, message):
        try:
            # Get API key from environment variable
            api_key = os.getenv('GROQ_API_KEY')
            if not api_key:
                return {'status': 'error', 'error': 'API key not configured'}

            # Initialize Groq client with API key from environment
            client = Groq(api_key=api_key)

            # Get relevant context from the database
            context = self._get_relevant_context(message)

            # Construct the prompt with context
            prompt = f"""You are a helpful AI assistant with access to the following database context:
            {context}

            User question: {message}

            Please provide a helpful response based on the available context."""

            # Get response from Groq
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful AI assistant that provides accurate information based on the given database context."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="mixtral-8x7b-32768",
                temperature=0.7,
                max_tokens=1024
            )

            return {
                'status': 'success',
                'response': chat_completion.choices[0].message.content
            }

        except Exception as e:
            _logger.error(f"Error processing message: {str(e)}")
            return {'status': 'error', 'error': str(e)}

    def _get_relevant_context(self, message):
        # Get relevant products
        products = request.env['product.template'].search([
            '|',
            ('name', 'ilike', message),
            ('description', 'ilike', message)
        ], limit=5)

        # Get relevant sales orders
        sales = request.env['sale.order'].search([
            '|',
            ('name', 'ilike', message),
            ('partner_id.name', 'ilike', message)
        ], limit=5)

        # Format context
        context = []
        if products:
            context.append("Products:")
            for product in products:
                context.append(f"- {product.name}: {product.description or 'No description'}")
        
        if sales:
            context.append("\nSales Orders:")
            for sale in sales:
                context.append(f"- {sale.name} for {sale.partner_id.name}")

        return "\n".join(context) if context else "No relevant context found." 