"""
Utility functions and helpers for the budget app.
"""
import json
from typing import Any, Dict, Optional

from django.http import HttpResponse
from django.template.loader import render_to_string


class HtmxResponseHelper:
    """
    Helper class for standardizing HTMX responses across budget views.
    Provides consistent API for toast messages, modal control, and page updates.
    """

    @staticmethod
    def success(
        message: str,
        close_modal: bool = False,
        update_summary: bool = False,
        redirect_url: Optional[str] = None,
        additional_triggers: Optional[Dict[str, Any]] = None,
        content: str = "",
    ) -> HttpResponse:
        """
        Create a success response with toast notification.

        Args:
            message: Success message to display in toast
            close_modal: Whether to close the modal after success
            update_summary: Whether to trigger budget summary update
            redirect_url: Optional URL to redirect to
            additional_triggers: Optional dict of additional HTMX triggers
            content: Optional HTML content to return

        Returns:
            HttpResponse with HX-Trigger header
        """
        triggers = {
            "showToast": {
                "message": message,
                "type": "success"
            }
        }

        if close_modal:
            triggers["closeModal"] = True

        if update_summary:
            triggers["update-summary"] = {}

        if additional_triggers:
            triggers.update(additional_triggers)

        response = HttpResponse(content)

        # Use HX-Trigger-After-Swap when content is provided to ensure
        # events are fired AFTER the DOM is updated with the new content
        if content:
            response["HX-Trigger-After-Swap"] = json.dumps(triggers)
        else:
            response["HX-Trigger"] = json.dumps(triggers)

        if redirect_url:
            response["HX-Redirect"] = redirect_url

        return response

    @staticmethod
    def error(
        message: str,
        form_errors: Optional[Dict] = None,
        status_code: int = 400,
        additional_triggers: Optional[Dict[str, Any]] = None,
        content: str = "",
    ) -> HttpResponse:
        """
        Create an error response with toast notification.

        Args:
            message: Error message to display in toast
            form_errors: Optional form validation errors
            status_code: HTTP status code (default 400)
            additional_triggers: Optional dict of additional HTMX triggers
            content: Optional HTML content to return (e.g., form with errors)

        Returns:
            HttpResponse with HX-Trigger header and error status
        """
        triggers = {
            "showToast": {
                "message": message,
                "type": "error"
            }
        }

        if form_errors:
            triggers["formErrors"] = form_errors

        if additional_triggers:
            triggers.update(additional_triggers)

        response = HttpResponse(content, status=status_code)
        response["HX-Trigger"] = json.dumps(triggers)

        return response

    @staticmethod
    def warning(
        message: str,
        additional_triggers: Optional[Dict[str, Any]] = None,
        content: str = "",
    ) -> HttpResponse:
        """
        Create a warning response with toast notification.

        Args:
            message: Warning message to display in toast
            additional_triggers: Optional dict of additional HTMX triggers
            content: Optional HTML content to return

        Returns:
            HttpResponse with HX-Trigger header
        """
        triggers = {
            "showToast": {
                "message": message,
                "type": "warning"
            }
        }

        if additional_triggers:
            triggers.update(additional_triggers)

        response = HttpResponse(content)
        response["HX-Trigger"] = json.dumps(triggers)

        return response

    @staticmethod
    def info(
        message: str,
        additional_triggers: Optional[Dict[str, Any]] = None,
        content: str = "",
    ) -> HttpResponse:
        """
        Create an info response with toast notification.

        Args:
            message: Info message to display in toast
            additional_triggers: Optional dict of additional HTMX triggers
            content: Optional HTML content to return

        Returns:
            HttpResponse with HX-Trigger header
        """
        triggers = {
            "showToast": {
                "message": message,
                "type": "info"
            }
        }

        if additional_triggers:
            triggers.update(additional_triggers)

        response = HttpResponse(content)
        response["HX-Trigger"] = json.dumps(triggers)

        return response

    @staticmethod
    def close_modal(
        update_summary: bool = False,
        additional_triggers: Optional[Dict[str, Any]] = None,
    ) -> HttpResponse:
        """
        Create a response that closes the modal.

        Args:
            update_summary: Whether to trigger budget summary update
            additional_triggers: Optional dict of additional HTMX triggers

        Returns:
            HttpResponse with HX-Trigger header
        """
        triggers = {"closeModal": True}

        if update_summary:
            triggers["update-summary"] = {}

        if additional_triggers:
            triggers.update(additional_triggers)

        response = HttpResponse()
        response["HX-Trigger"] = json.dumps(triggers)

        return response

    @staticmethod
    def redirect(url: str, message: Optional[str] = None) -> HttpResponse:
        """
        Create a redirect response.

        Args:
            url: URL to redirect to
            message: Optional success message to show after redirect

        Returns:
            HttpResponse with HX-Redirect header
        """
        response = HttpResponse()
        response["HX-Redirect"] = url

        if message:
            triggers = {
                "showToast": {
                    "message": message,
                    "type": "success"
                }
            }
            response["HX-Trigger"] = json.dumps(triggers)

        return response

    @staticmethod
    def update_summary() -> HttpResponse:
        """
        Create a response that triggers budget summary update.

        Returns:
            HttpResponse with HX-Trigger header
        """
        response = HttpResponse()
        response["HX-Trigger"] = json.dumps({"update-summary": {}})

        return response

    @staticmethod
    def render_and_trigger(
        template: str,
        context: Dict[str, Any],
        triggers: Dict[str, Any],
        status_code: int = 200,
    ) -> HttpResponse:
        """
        Render a template and attach HTMX triggers.

        Args:
            template: Template path to render
            context: Template context
            triggers: Dict of HTMX triggers
            status_code: HTTP status code

        Returns:
            HttpResponse with rendered content and HX-Trigger header
        """
        content = render_to_string(template, context)
        response = HttpResponse(content, status=status_code)
        response["HX-Trigger"] = json.dumps(triggers)

        return response
