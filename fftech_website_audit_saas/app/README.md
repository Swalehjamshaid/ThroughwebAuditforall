
# Completed Django App Folder (`app/`)

Ready-to-integrate Django app aligned with your templates.

## Integrate
1. Add `'app'` to `INSTALLED_APPS` in `settings.py`.
2. Include app URLs in your project `urls.py`:
   ```python
   from django.urls import path, include

   urlpatterns = [
       path('', include('app.urls')),
   ]
   ```
3. Migrate: `python manage.py makemigrations app && python manage.py migrate`.
4. Run: `python manage.py runserver`.
