# gunicornconfig.py

import multiprocessing

# Binding
bind = "0.0.0.0:5001"

# Worker settings
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"  # Async workers; good for Flask
timeout = 120

# Logging
accesslog = "/www/wwwroot/KODEMAPA-EXAMPAD/logs/gunicorn_access.log"
errorlog = "/www/wwwroot/KODEMAPA-EXAMPAD/logs/gunicorn_error.log"
loglevel = "info"

# Daemonize (optional; remove if using systemd or supervisor)
# daemon = True

# App import path (set if not using CLI)
# wsgi_app = "run:app"  # Optional if specified in command

# PID file
pidfile = "/tmp/gunicorn_exampad.pid"