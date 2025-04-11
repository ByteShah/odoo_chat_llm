import re
import logging
from odoo import http
from odoo.http import request
from groq import Groq
import json

_logger = logging.getLogger(__name__)

# Initialize Groq client with your API key
client = Groq(api_key="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")

class WebsiteChat(http.Controller):

    @http.route(['/llm/chat'], type='http', auth='public', website=True)
    def chat_page(self, **kw):
        """Render the website chat page."""
        return request.render('odoo_chat_llm.website_chat_page', {})

    @http.route('/llm/chat/message', type='json', auth='public', methods=['POST'], csrf=False)
    def process_chat_message(self, **post):
        """Process chat message and generate LLM response"""
        try:
            data = json.loads(request.httprequest.data)
            user_message = data.get('message', '').strip()
            if not user_message:
                return {'error': 'Please enter a valid message.'}

            # Generate ORM query
            generated_query = self._generate_orm_query(user_message)
            if not generated_query:
                return {'error': 'Could not generate valid query.'}

            # Execute query safely
            query_result = self._execute_orm_query(generated_query)
            if not query_result:
                return {'error': 'No results found for your query.'}

            final_response = self._generate_final_response(user_message, query_result)
            return {'response': final_response}

        except json.JSONDecodeError:
            return {'error': 'Invalid request format.'}
        except Exception as e:
            _logger.error("Processing error: %s", str(e), exc_info=True)
            return {'error': 'An error occurred while processing your request.'}

    def _generate_orm_query(self, user_message):
        """Generate ORM query from natural language input"""
        prompt = f"""Translate this natural language query into valid Odoo ORM code:
        {user_message}
        - Use 'env' for Odoo environment
        - Return only Python code without comments
        - reposne should be like 'env['res.users'].sudo().search_count([])' this kind of python only I don't want any other thing or code"""
        
        try:
            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            raw_code = response.choices[0].message.content.strip()
            return self._extract_python_code(raw_code)
        except Exception as e:
            _logger.error("Query generation failed: %s", str(e))
            return None

    def _extract_python_code(self, raw_text):
        """Extract Python code from LLM response"""
        code_match = re.search(r"```(?:python)?(.*?)```", raw_text, re.DOTALL)
        return code_match.group(1).strip() if code_match else raw_text

    def _execute_orm_query(self, generated_code):
        """Safely execute generated ORM code and return results"""
        local_vars = {'env': request.env, 'query_result': None}
        
        try:
            # Add explicit assignment if missing
            if not generated_code.strip().startswith('query_result'):
                generated_code = f"query_result = {generated_code.strip().rstrip(';')}"

            # Create safe execution environment
            safe_globals = {
                '__builtins__': {
                    'super': super,
                    'float': float,
                    'int': int,
                    'str': str,
                    'bool': bool
                }
            }

            exec(generated_code, safe_globals, local_vars)

            # return self._format_records(local_vars.get('query_result'))
            return local_vars.get('query_result')
        
        except Exception as e:
            _logger.error("Execution error: %s\nCode: %s", str(e), generated_code)
            return None

    def _format_records(self, records):
        """Format Odoo records for LLM consumption"""
        if not records:
            return "No results found"
            
        try:
            if len(records) > 10:
                return f"Found {len(records)} matching records. Showing first 10:\n" + "\n".join(
                    str(rec.display_name) for rec in records[:10]
                )
            return "\n".join(str(rec.display_name) for rec in records)
        except AttributeError:
            return str(records)

    def _generate_final_response(self, user_message, query_result):
        """Generate natural language response from query results"""
        prompt = f"""User asked: {user_message}
        Database query returned these results:
        {query_result}
        Create a helpful response in natural language."""
        
        try:
            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            _logger.error("Response generation failed: %s", str(e))
            return "I'm having trouble generating a response. Here are the raw results:\n" + query_result
