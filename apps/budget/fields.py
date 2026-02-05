"""
Custom form fields for the budget app.
"""
from datetime import timedelta
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError


class DurationField(forms.DurationField):
    """
    Custom duration field that handles multiple input formats:
    - HH:MM:SS
    - HH:MM
    - HH (hours only)
    - timedelta objects
    """

    @staticmethod
    def parse_duration(value) -> Optional[timedelta]:
        """
        Parse duration from various string formats or timedelta objects.

        Args:
            value: Duration value (string or timedelta)

        Returns:
            timedelta object or None if value is empty

        Raises:
            ValidationError: If format is invalid
        """
        if not value:
            return None

        if isinstance(value, timedelta):
            return value

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

            try:
                # Try to parse as HH:MM:SS, HH:MM, or HH
                parts = [int(p) for p in value.split(":")]

                if len(parts) == 3:
                    # HH:MM:SS
                    hours, minutes, seconds = parts
                    return timedelta(hours=hours, minutes=minutes, seconds=seconds)
                elif len(parts) == 2:
                    # HH:MM
                    hours, minutes = parts
                    return timedelta(hours=hours, minutes=minutes)
                elif len(parts) == 1:
                    # HH (hours only)
                    hours = parts[0]
                    return timedelta(hours=hours)
                else:
                    raise ValidationError("Formato de duração inválido. Use HH:MM ou HH:MM:SS")

            except (ValueError, TypeError) as e:
                raise ValidationError(
                    f"Formato de duração inválido: '{value}'. Use HH:MM ou HH:MM:SS"
                ) from e

        raise ValidationError(f"Tipo de valor inválido para duração: {type(value)}")

    def to_python(self, value):
        """
        Convert input value to timedelta object.

        Args:
            value: Input value from form

        Returns:
            timedelta object or None
        """
        if value in self.empty_values:
            return None

        try:
            # Try our custom parser first
            return self.parse_duration(value)
        except ValidationError:
            # If custom parser fails, try Django's default parser
            return super().to_python(value)

    def prepare_value(self, value):
        """
        Format timedelta for display in form field.

        Args:
            value: timedelta object

        Returns:
            Formatted string (HH:MM:SS)
        """
        if isinstance(value, timedelta):
            total_seconds = int(value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return value
