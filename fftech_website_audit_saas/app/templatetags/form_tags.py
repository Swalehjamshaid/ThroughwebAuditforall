
from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    try:
        base = field.field.widget.attrs.get('class', '')
        merged = (base + ' ' + css).strip()
        attrs = dict(field.field.widget.attrs)
        attrs['class'] = merged
        return field.as_widget(attrs=attrs)
    except Exception:
        return field
