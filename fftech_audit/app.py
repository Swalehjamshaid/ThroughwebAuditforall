
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FF Tech AI • Website Audit</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap
  /static/app.css
  https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js</script>
  /static/app.js</script>
</head>
<body class="font-inter theme-dark">
  <header class="hdr">
    <div class="container hdr__bar">
      <div class="hdr__brand">
        <div class="logo-dot"></div>
        <strong>FF Tech AI • Website Audit</strong>
      </div>
      <div class="hdr__actions">
        <button class="btn ghost" onclick="toggleTheme()">Toggle Theme</button>
        <button class="btn ghost" onclick="logout()">Logout</button>
      </div>
    </div>
    <div class="hdr__gradient"></div>
  </header>
  <main class="container page">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
