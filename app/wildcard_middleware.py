"""
Flask middleware to handle URL-encoded asterisks in query parameters.

This middleware processes incoming requests to preserve the distinction between
literal asterisks (URL-encoded as %2A) and wildcard asterisks (passed as *).
"""

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from flask import request
from werkzeug.datastructures import ImmutableMultiDict

from api.wildcard_utils import LITERAL_ASTERISK_PLACEHOLDER


class WildcardMiddleware:
    """
    Flask middleware to preserve URL-encoded asterisks for wildcard filtering.
    
    This middleware intercepts incoming requests and replaces URL-encoded asterisks
    (%2A) with a special placeholder before the request is processed by the
    application. This allows the filtering logic to distinguish between literal
    asterisks and wildcard asterisks.
    """
    
    def __init__(self, app):
        self.app = app
        self.app.before_request(self.process_request)
    
    def process_request(self):
        """
        Process the incoming request to preserve URL-encoded asterisks.
        
        This method is called before each request is processed. It modifies
        the request's query string to replace %2A with a placeholder.
        """
        if not request.query_string:
            return
        
        # Get the raw query string
        query_string = request.query_string.decode('utf-8')
        
        # Check if there are any URL-encoded asterisks to process
        if '%2A' not in query_string.upper():
            return
        
        # Replace URL-encoded asterisks with placeholder
        modified_query_string = self._preserve_url_encoded_asterisks(query_string)
        
        if modified_query_string != query_string:
            # Parse the modified query string
            parsed_args = parse_qs(modified_query_string, keep_blank_values=True)
            
            # Convert to the format expected by Flask
            new_args = {}
            for key, values in parsed_args.items():
                if len(values) == 1:
                    new_args[key] = values[0]
                else:
                    new_args[key] = values
            
            # Replace the request args with the modified version
            # Note: This is a bit of a hack, but it's the cleanest way to modify
            # the request args before they're processed by connexion
            request.args = ImmutableMultiDict(new_args)
    
    def _preserve_url_encoded_asterisks(self, query_string: str) -> str:
        """
        Replace URL-encoded asterisks (%2A) with a placeholder.
        
        Args:
            query_string: Raw query string from the HTTP request
            
        Returns:
            Modified query string with %2A replaced by placeholder
        """
        # Replace %2A (case insensitive) with our placeholder
        return re.sub(r'%2[aA]', LITERAL_ASTERISK_PLACEHOLDER, query_string)


def init_wildcard_middleware(app):
    """
    Initialize the wildcard middleware for the Flask app.
    
    Args:
        app: Flask application instance
    """
    WildcardMiddleware(app)