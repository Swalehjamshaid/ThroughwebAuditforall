<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{% block title %}{{ UI_BRAND_NAME }} | Professional AI Website Audit{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />

    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

    <link rel="stylesheet" href="{{ url_for('static', path='/fftech.css') }}">

    {% block head_extra %}{% endblock %}

    <style>
        :root {
            --primary: #0057D9;
            --accent: #1ABC9C;
            --dark: #0c1220;
            --glass: rgba(255, 255, 255, 0.04);
            --glass-border: rgba(255, 255, 255, 0.08);
        }

        body {
            background: var(--dark);
            color: #e6ecf3;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Modern UI Components */
        .glass-card {
            background: var(--glass);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }

        .navbar {
            backdrop-filter: blur(10px);
            background: rgba(12, 18, 32, 0.85) !important;
            border-bottom: 1px solid var(--glass-border);
        }

        .btn-ai-primary {
            background: linear-gradient(135deg, var(--primary), #0072ff);
            border: none;
            color: white;
            padding: 8px 20px;
            border-radius: 8px;
            transition: 0.3s;
        }

        .btn-ai-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0, 87, 217, 0.4);
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark sticky-top mb-5">
        <div class="container">
            <a class="navbar-brand fw-bold d-flex align-items-center" href="/">
                <i class="fa-solid fa-microchip me-2 text-info"></i>
                {{ UI_BRAND_NAME }}
            </a>

            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>

            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto align-items-center">
                    {% if user %}
                        <li class="nav-item me-3">
                            <span class="text-secondary small d-block">Logged in as</span>
                            <span class="fw-medium text-info">{{ user.email }}</span>
                        </li>
                        <li class="nav-item">
                            <a href="/auth/dashboard" class="nav-link">Dashboard</a>
                        </li>
                        <li class="nav-item">
                            <a href="/auth/logout" class="btn btn-sm btn-outline-danger ms-2">Logout</a>
                        </li>
                    {% else %}
                        <li class="nav-item">
                            <a href="/auth/login" class="nav-link">Login</a>
                        </li>
                        <li class="nav-item">
                            <a href="/auth/register" class="btn-ai-primary ms-2">Get Started</a>
                        </li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <main class="container">
        {% block content %}{% endblock %}
    </main>

    <footer class="container text-center py-5 mt-auto">
        <hr class="border-secondary opacity-25">
        <p class="text-secondary small">
            &copy; 2026 {{ UI_BRAND_NAME }} AI Diagnostics. <br>
            Powered by Automated SEO Engine v2.4.0
        </p>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts_extra %}{% endblock %}
</body>
</html>
