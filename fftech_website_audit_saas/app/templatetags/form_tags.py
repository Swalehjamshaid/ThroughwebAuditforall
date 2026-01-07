
from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    if hasattr(field, 'field') and field.field.widget:
        existing = field.field.widget.attrs.get('class', '')
        classes = f"{existing} {css}".strip()
        field.field.widget.attrs['class'] = classes
    return field
